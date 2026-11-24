import json
import re
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from urllib import parse

from playwright.sync_api import Page

from utils import browser_ini, is_mikistyle

"""
ログイン時にロボット検知がある場合は、cmdで以下コマンド経由で事前にログインし、ログインデータを作ること
r"C:/Program Files/Google/Chrome/Application/chrome.exe" --user-data-dir="C:/Users/boost/Documents/PrivateSourceTree/operate-buyma/user_data/chrome_user_data/"
"""


@dataclass
class ProductData:
    """商品データ"""

    url: str
    gender: str | None = None
    category: list[str] | None = None
    brand: str = ""
    title: str = ""
    product_code: str = ""
    price: int | None = None
    size: list[str] | None = None
    model_info: str | None = None
    description: str | None = None
    material: str | None = None
    origin: str | None = None
    img: list[str] = field(default_factory=list)


class SSenseScraper:
    """SSENSE商品スクレイパー（都度保存・再開対応版）"""

    BASE_URL = "https://www.ssense.com/ja-jp"
    DEFAULT_USER_DATA_DIR = Path("../user_data/chrome_user_data")
    # Cloudflare再接続時の待機秒数
    CLOUDFLARE_WAIT_SEC = 30

    def __init__(self, headless: bool = False):
        self.headless = headless
        self._ensure_user_data_dir()

    def _ensure_user_data_dir(self) -> None:
        if not self.DEFAULT_USER_DATA_DIR.exists():
            self.DEFAULT_USER_DATA_DIR.mkdir(parents=True, exist_ok=True)
            print(f"✓ user-data-dir を作成: {self.DEFAULT_USER_DATA_DIR}")
        else:
            print(f"✓ user-data-dir を読込: {self.DEFAULT_USER_DATA_DIR}")

    def _load_existing_urls(self, output_file: Path) -> set[str]:
        """既存ファイルから取得済みURLを読み込む"""
        if not output_file.exists():
            return set()
        try:
            data = json.loads(output_file.read_text(encoding="utf-8"))
            urls = {item["url"] for item in data if "url" in item}
            print(f"✓ 取得済み {len(urls)} 件を読込: {output_file}")
            return urls
        except Exception as e:
            print(f"⚠ 既存ファイル読込エラー: {e}")
            return set()

    def _append_to_file(self, output_file: Path, product: ProductData) -> None:
        """商品データをファイルに追記"""
        data = []
        if output_file.exists():
            try:
                data = json.loads(output_file.read_text(encoding="utf-8"))
            except Exception:
                pass
        data.append(asdict(product))
        output_file.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def _safe_get_text(self, page: Page, selector: str, default: str = "") -> str:
        try:
            elem = page.locator(selector).first
            if elem.count() > 0:
                return elem.inner_text().strip()
        except Exception:
            pass
        return default

    # ── Cloudflare BOTチェック対策 ──────────────────────────────────────

    def _detect_cloudflare(self, page: Page) -> bool:
        """Cloudflareチャレンジページが表示されているかを判定"""
        try:
            title = page.title()
            body_text = page.locator("body").inner_text() or ""
            return (
                "Just a moment" in title
                or "しばらくお待ちください" in title
                or "Checking your browser" in body_text
                or "Cloudflare" in body_text
                or "Please enable JavaScript" in body_text
            )
        except Exception:
            return False

    def _handle_cloudflare(
        self, context, page: Page, url: str
    ) -> tuple:
        """Cloudflare検出時にブラウザを再起動して再接続する

        Returns:
            tuple: (new_context, new_page)
        """
        print("\n" + "=" * 60)
        print("⚠️ Cloudflare challenge detected. ブラウザを再起動します...")
        print(f"  {self.CLOUDFLARE_WAIT_SEC}秒待機してから再接続します")
        print("=" * 60 + "\n")

        # コンテキスト（ブラウザ）を閉じる
        try:
            context.close()
        except Exception:
            pass

        time.sleep(self.CLOUDFLARE_WAIT_SEC)

        # ブラウザを再起動
        print("🔄 ブラウザを再起動中...")
        new_context, new_page = browser_ini(
            str(self.DEFAULT_USER_DATA_DIR), headless=self.headless
        )

        # 元のURLに再アクセス
        new_page.goto(url, timeout=60000, wait_until="domcontentloaded")
        time.sleep(5)

        print("✓ 再接続完了\n")
        return new_context, new_page

    def _goto_with_cloudflare_guard(
        self, context, page: Page, url: str, **goto_kwargs
    ) -> tuple:
        """page.gotoを実行し、Cloudflareが検出された場合はブラウザ再起動して再試行する

        Returns:
            tuple: (context, page) — 再起動が発生した場合は新しいオブジェクト
        """
        page.goto(url, **goto_kwargs)
        if self._detect_cloudflare(page):
            context, page = self._handle_cloudflare(context, page, url)
        return context, page

    # ── 商品データ抽出 ──────────────────────────────────────────────────

    def _extract_price(self, page: Page) -> int | None:
        try:
            price_text = self._safe_get_text(page, '[data-test="regularPriceText"]')
            if match := re.search(r"¥([\d,]+)", price_text):
                return int(match.group(1).replace(",", ""))
        except Exception:
            pass
        return None

    def _extract_sizes(self, page: Page) -> list[str] | None:
        sizes, seen = [], set()
        try:
            for option in page.locator("#size-dropdown option").all():
                if option.get_attribute("disabled"):
                    continue
                text = option.inner_text()
                if text and text != "サイズの選択":
                    # 在庫なしのサイズはスキップ
                    if "在庫なし" in text:
                        continue
                    clean = re.sub(r"\s*-\s*残り\s*\d+", "", text).strip()
                    if clean and clean not in seen:
                        sizes.append(clean)
                        seen.add(clean)
        except Exception:
            pass
        return sizes if sizes else None

    def _extract_model_info(self, page: Page) -> str | None:
        """モデル情報（身長・着用サイズ等）を抽出"""
        try:
            # ページ全体のspanから「モデル」「身長」を含むテキストを検索
            for elem in page.locator("span").all():
                text = elem.inner_text()
                if ("モデル" in text or "身長" in text) and len(text) < 200:
                    return text.strip()
        except Exception:
            pass
        return None

    def _extract_origin(self, page: Page) -> str | None:
        """原産国（例: イタリア製）を抽出"""
        try:
            # 商品説明の次のdiv内のspanを検索
            for elem in page.locator("div.whitespace-pre-line + div span").all():
                text = elem.inner_text().strip()
                if match := re.search(r"([^\s]+)\s*製[。]?", text):
                    return match.group(1) + "製"
        except Exception:
            pass
        return None

    def _extract_images(self, page: Page, product_code: str = "") -> list[str]:
        images = []
        try:
            # メインカルーセル内の画像を取得（関連商品の画像を排除）
            selector = 'section[aria-roledescription="carousel"] img[data-srcset], section[aria-roledescription="carousel"] img[srcset]'
            img_locators = page.locator(selector).all()
            
            # カルーセルが見つからない場合のフォールバック
            if not img_locators:
                img_locators = page.locator("img[data-srcset], img[srcset]").all()

            for img in img_locators:
                srcset = img.get_attribute("data-srcset") or img.get_attribute("srcset") or ""
                if not srcset:
                    continue
                
                # srcsetの中からすべてのURLを抽出し、最後のもの（通常は最高画質 w_1920等）を取得
                urls = re.findall(r"https?://[^\s]+", srcset)
                if urls:
                    url = urls[-1]
                    path = parse.urlparse(url).path
                    if "images/" in path:
                        img_path = path.split("images/", 1)[1]
                        
                        # product_codeがある場合は、一致しない画像（おすすめ商品など）をスキップ
                        if product_code and product_code not in img_path:
                            continue
                            
                        # ベース画像ID（262441F122007_1 など）を使って重複排除
                        base_id_match = re.search(r"/([A-Z0-9]+_\d+)/", img_path)
                        if base_id_match:
                            base_id = base_id_match.group(1)
                            if not any(f"/{base_id}/" in existing for existing in images):
                                images.append(img_path)
                        else:
                            if img_path not in images:
                                images.append(img_path)
        except Exception:
            pass
        return images

    def _extract_product_code(self, page: Page) -> str:
        """SKU/商品コードを抽出（例: 262195M192030）"""
        try:
            for elem in page.locator("span").all():
                text = elem.inner_text().strip()
                # SKUパターン: 英数字混合で6文字以上、大文字を含む
                if re.fullmatch(r"[A-Z0-9]{6,}", text):
                    return text
        except Exception:
            pass
        return ""

    def _get_product_key(self, url: str) -> str:
        """URLから一意キーを抽出（スキップ判定用）"""
        return parse.urlparse(url).path.split("/", 4)[-1]

    def _extract_category(self, page: Page) -> list[str] | None:
        """HTML内のスクリプトからカテゴリー（categorySeoKeyword）を抽出"""
        try:
            content = page.content()
            if match := re.search(r'\\?"categorySeoKeyword\\?"\s*:\s*\\?"([^"\\]+)', content):
                return [match.group(1)]
        except Exception:
            pass
        return None

    def _extract_material(self, page: Page) -> str | None:
        """素材情報を抽出"""
        try:
            # 商品説明の次のdiv内のspanを検索（素材と原産国が含まれる）
            for elem in page.locator("div.whitespace-pre-line + div span").all():
                text = elem.inner_text().strip()
                if text and not re.search(r"[^\s]+\s*製[。]?", text):
                    return text
        except Exception:
            pass
        return None

    def scrape_product(
        self, context, page: Page, url: str
    ) -> tuple[ProductData | None, object, Page]:
        """商品ページをスクレイピングする

        Returns:
            tuple: (ProductData | None, context, page)
                Cloudflare再接続によりcontext/pageが差し替わる可能性があるためタプルで返す
        """
        try:
            context, page = self._goto_with_cloudflare_guard(
                context, page, url, wait_until="domcontentloaded"
            )

            # 画像が読み込まれるまで少し待つ
            page.wait_for_timeout(2000)

            if self._extract_price(page) is None:
                return None, context, page

            url_parts = parse.urlparse(url).path.split("/")

            category = self._extract_category(page)


            # ブランド名: h1内の最初のリンクテキスト
            brand = self._safe_get_text(page, "h1 a span")

            # タイトル: h1のテキスト全体からブランド名を除去
            h1_text = self._safe_get_text(page, "h1")
            title = h1_text.replace(brand, "").strip() if brand and h1_text else h1_text

            # 説明文: whitespace-pre-line クラスのdiv
            description = self._safe_get_text(page, "div.whitespace-pre-line")
            
            product_code = self._extract_product_code(page)

            product = ProductData(
                url=self._get_product_key(url),
                gender=url_parts[2] if len(url_parts) > 2 else None,
                category=category,
                brand=brand,
                title=title,
                product_code=product_code,
                price=self._extract_price(page),
                size=self._extract_sizes(page),
                model_info=self._extract_model_info(page),
                description=description,
                material=self._extract_material(page),
                origin=self._extract_origin(page),
                img=self._extract_images(page, product_code=product_code),
            )
            return product, context, page
        except Exception as e:
            print(f"  ✗ エラー ({url}): {e}")
            return None, context, page

    def _collect_product_urls(self, page: Page) -> list[str]:
        urls = []
        for script in page.locator('script[type="application/ld+json"]').all():
            try:
                data = json.loads(script.inner_text())
                if "url" in data and "/product/" in data["url"]:
                    # data["url"] が絶対URLの場合はそのまま使用、相対パスの場合のみBASE_URLを付与
                    product_url = data["url"]
                    if not product_url.startswith("http"):
                        product_url = f"{self.BASE_URL}{product_url}"
                    urls.append(product_url)
            except Exception:
                continue
        return urls

    def _get_max_pages(self, page: Page) -> int:
        """ページネーションから最大ページ数を取得"""
        try:
            # desktop用ページネーション内の全ページリンクからページ番号を抽出
            page_links = page.locator('div[data-testid="desktop"] a[href*="page="]').all()
            if page_links:
                max_page = 1
                for link in page_links:
                    href = link.get_attribute("href") or ""
                    if match := re.search(r"page=(\d+)", href):
                        max_page = max(max_page, int(match.group(1)))
                return max_page
        except Exception:
            pass
        return 1  # デフォルト

    def _scrape_listing_with_page(
            self,
            context,
            page,
            start_url: str,
            output_file: str,
            scraped_urls: set,
            max_pages: int | None = None,
            delay: float = 1.0,
    ) -> tuple[dict, object, Page]:
        """既存のページを使って一覧スクレイピングを実行（ブラウザ共有用内部メソッド）

        Returns:
            tuple: (stats, context, page)
                Cloudflare再接続によりcontext/pageが差し替わる可能性があるためタプルで返す
        """
        output_path = Path(output_file)
        stats = {"total": 0, "new": 0, "skipped": 0, "errors": 0}

        # 最初のページをロードして max_pages を取得（Cloudflareガード付き）
        context, page = self._goto_with_cloudflare_guard(
            context, page, start_url, wait_until="domcontentloaded"
        )
        time.sleep(delay * 2)
        if max_pages is None:
            max_pages = self._get_max_pages(page)
            print(f"最終ページ: {max_pages}")

        for page_num in range(1, max_pages + 1):
            if page_num > 1:
                list_url = f"{start_url}?page={page_num}"
                print(f"\n=== ページ {page_num}: {list_url} ===")
                context, page = self._goto_with_cloudflare_guard(
                    context, page, list_url, wait_until="domcontentloaded"
                )
                time.sleep(delay * 2)
            else:
                list_url = start_url
                print(f"\n=== ページ {page_num}: {list_url} ===")

            product_urls = self._collect_product_urls(page)
            print(f"  発見: {len(product_urls)} 件")
            stats["total"] += len(product_urls)

            for i, url in enumerate(product_urls, 1):
                product_key = self._get_product_key(url)
                short_name = url.split("/")[-1][:35]

                # スキップ判定
                if product_key in scraped_urls:
                    print(f"  [{i}/{len(product_urls)}] ⏭ {short_name}")
                    stats["skipped"] += 1
                    continue

                print(f"  [{i}/{len(product_urls)}] ⏳ {short_name}")

                product, context, page = self.scrape_product(context, page, url)
                if product and product.img:
                    self._append_to_file(output_path, product)
                    scraped_urls.add(product_key)
                    print(f"    ✓ {product.brand} - {product.title[:25]}")
                    stats["new"] += 1
                else:
                    stats["errors"] += 1

                time.sleep(delay)

        return stats, context, page


    def scrape_categories(
            self,
            category_urls: list[str],
            output_file: str,
            max_pages: int | None = None,
            delay: float = 1.0,
    ) -> dict:
        """複数カテゴリURLを1つのブラウザで順番にスクレイピング（ブラウザ起動コスト節約）"""
        output_path = Path(output_file)
        # 全カテゴリ共通のスキップ判定セットを共有
        scraped_urls = self._load_existing_urls(output_path)
        total_stats = {"total": 0, "new": 0, "skipped": 0, "errors": 0}

        context, page = browser_ini(
            str(self.DEFAULT_USER_DATA_DIR), headless=self.headless
        )

        try:
            for category_url in category_urls:
                print(f"\n{'#' * 50}")
                print(f"# カテゴリ: {category_url}")
                print(f"{'#' * 50}")
                stats, context, page = self._scrape_listing_with_page(
                    context, page, category_url, output_file, scraped_urls, max_pages, delay
                )
                for key in total_stats:
                    total_stats[key] += stats[key]
        except Exception as e:
            print(f"\nエラー: {e}")
            import traceback
            traceback.print_exc()
        finally:
            context.close()

        print(f"\n{'=' * 40} 全カテゴリ合計 {'=' * 40}")
        print(f"総発見数: {total_stats['total']}")
        print(f"新規取得: {total_stats['new']}")
        print(f"スキップ: {total_stats['skipped']}")
        print(f"エラー:   {total_stats['errors']}")
        print(f"保存先:   {output_path}")
        print(f"{'=' * 40}")
        return total_stats


if __name__ == "__main__":
    scraper = SSenseScraper()

    # ── スクレイピング対象カテゴリURLを列挙 ──────────────────────────────
    # 例: 全商品を対象にする場合は "/women" や "/men" のみ指定
    # 特定カテゴリのみにする場合は対象URLを個別に列挙する
    if is_mikistyle:
        category_urls = [
            "https://www.ssense.com/ja-jp/women/jackets-coats",
            "https://www.ssense.com/ja-jp/women/sweaters",
            "https://www.ssense.com/ja-jp/women/boots",
            "https://www.ssense.com/ja-jp/women/jeans",
        ]
        output_file = "women.json"
    else:
        category_urls = [
            # "https://www.ssense.com/ja-jp/men/shoes",
            # "https://www.ssense.com/ja-jp/men/accessories",
            # "https://www.ssense.com/ja-jp/men/bags",
            "https://www.ssense.com/ja-jp/men/tops"
        ]
        output_file = "men.json"
    # ────────────────────────────────────────────────────────────────────

    # ブラウザを1回だけ起動して全カテゴリをまとめて処理
    scraper.scrape_categories(category_urls, output_file=output_file)

