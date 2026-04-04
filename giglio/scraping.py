import json
import re
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from urllib import parse

from playwright.sync_api import Page

import utils
from utils import browser_ini, is_mikistyle


@dataclass
class ProductData:
    """商品データ"""

    url: str
    gender: str | None = None
    category: list[str] | None = None
    brand: str = ""
    title: str = ""
    price: int | None = None
    size: list[str] | None = None
    model_info: str | None = None
    description: str | None = None
    material: str | None = None
    img: list[str] = field(default_factory=list)


class GiglioScraper:
    """Giglio商品スクレイパー"""

    BASE_URL = "https://www.giglio.com"
    DEFAULT_USER_DATA_DIR = Path("../user_data/chrome_user_data")

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
        # 親ディレクトリが存在することを確認
        output_file.parent.mkdir(parents=True, exist_ok=True)
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
                # inner_text() は非表示要素で空を返すため、text_content() を使用
                return elem.text_content().strip()
        except Exception:
            pass
        return default

    def _safe_get_attr(self, page: Page, selector: str, attr: str) -> str | None:
        try:
            elem = page.locator(selector).first
            if elem.count() > 0:
                value = elem.get_attribute(attr)
                return value.strip() if value else None
        except Exception:
            pass
        return None

    def _extract_price(self, page: Page) -> int | None:
        try:
            # meta tagを優先
            price_content = self._safe_get_attr(page, 'meta[itemprop="price"]', "content")
            if price_content:
                return int(float(price_content))

            # またはテキストから
            price_text = self._safe_get_text(page, '.product-page-price__prices b')
            if match := re.search(r"¥([\d,]+)", price_text):
                return int(match.group(1).replace(",", ""))
        except Exception:
            pass
        return None

    def _extract_sizes(self, page: Page) -> list[str] | None:
        sizes, seen = [], set()
        try:
            # セレクトボックスから取得
            options = page.locator("select.product-page-sizes__select option").all()
            for option in options:
                text = option.inner_text().strip()
                if not text or "選択してください" in text or "通知を受け取る" in text:
                    continue

                # "IT 44 | ¥62,543" のような形式からサイズ部分を抽出。½ を .5 に置換
                clean = text.split("|")[0].strip().replace("½", ".5")

                if clean and clean not in seen:
                    sizes.append(clean)
                    seen.add(clean)
        except Exception:
            pass
        return sizes if sizes else None

    def _extract_images(self, page: Page) -> list[str]:
        images = []
        try:
            # JSON-LDから取得
            scripts = page.locator('script[type="application/ld+json"]').all()
            for script in scripts:
                try:
                    data = json.loads(script.inner_text())
                    # ProductGroup or Product
                    if isinstance(data, list):
                        data = data[0]

                    if "hasVariant" in data:
                        for variant in data["hasVariant"]:
                            if "image" in variant:
                                images.extend(variant["image"])
                    elif "image" in data:
                        if isinstance(data["image"], list):
                            images.extend(data["image"])
                        else:
                            images.append(data["image"])
                except Exception:
                    continue

            if not images:
                # ギャラリーから直接取得
                for img in page.locator(".product-page-gallery__item img").all():
                    src = img.get_attribute("src")
                    if src and src not in images:
                        images.append(src)
        except Exception:
            pass

        # Note: Giglioでは商品によりドメインが分散（img.giglio.com / media-catalog.giglio.com）するため、
        # 完全URLで保存するように変更
        unique_images = list(dict.fromkeys(images))
        return unique_images

    def _extract_material(self, page: Page) -> str | None:
        """詳細項目から『素材』を探して抽出（非表示でも取得可能）"""
        try:
            # tab_2 内からラベル要素をすべて取得
            label_selector = '.product-page-details__tabs__tab[data-tab-index="tab_2"] .product-page-details__tabs__tab__p-title'
            items = page.locator(label_selector).all()
            for item in items:
                text = item.text_content()
                if text and "素材" in text:
                    return text.replace("素材", "").strip()
        except Exception:
            pass
        return None

    def _extract_description(self, page: Page) -> str | None:
        """「商品の説明」タブの内容を取得（非表示でも取得可能）"""
        text = self._safe_get_text(page,
                                   '.product-page-details__tabs__tab[data-tab-index="tab_1"] .product-page-details__tabs__tab__container')
        if not text:
            return None

        # 2つ目以降の「・」または「•」で改行を入れる。最初のものは strip() で改行が除去される。
        text = re.sub(r'\s*([•・])', r'\n\1', text)
        return text.strip()

    def _get_product_key(self, url: str) -> str:
        """URLからベースURLと/ja-jpを除去し、さらに先頭のスラッシュを削除して一意キーとする"""
        parsed = parse.urlparse(url)
        path = parsed.path
        if path.startswith("/ja-jp"):
            path = path[6:]
        path = path.lstrip("/")
        if parsed.query:
            path = f"{path}?{parsed.query}"
        return path

    def scrape_product(self, page: Page, url: str) -> ProductData | None:
        try:
            page.goto(url, wait_until="domcontentloaded")
            page.wait_for_timeout(2000)

            price = self._extract_price(page)
            if price is None:
                return None

            brand = self._safe_get_text(page, "strong.product-page-header__brand")
            title = self._safe_get_text(page, "h1.product-page-header__title")

            # パンくずから性別とカテゴリを推測
            breadcrumbs = page.locator(".product-page-breadcrumbs li").all()
            gender = None
            category = []

            if len(breadcrumbs) > 2:
                gender = breadcrumbs[1].inner_text().strip()
                # 3番目以降をカテゴリとする (2番目はブランド名のはず)
                for i in range(3, len(breadcrumbs)):
                    category.append(breadcrumbs[i].inner_text().strip())

            description = self._extract_description(page)
            material = self._extract_material(page)

            return ProductData(
                url=self._get_product_key(url),
                gender=gender,
                category=category,
                brand=brand,
                title=title,
                price=price,
                size=self._extract_sizes(page),
                description=description,
                material=material,
                img=self._extract_images(page),
            )
        except Exception as e:
            print(f"  ✗ エラー ({url}): {e}")
            return None

    def _collect_product_urls(self, page: Page) -> list[str]:
        urls = []
        for a in page.locator('article.prod-card a[itemprop="url"]').all():
            href = a.get_attribute("href")
            if href:
                full_url = parse.urljoin(self.BASE_URL, href)
                urls.append(full_url)
        return urls

    def _get_max_pages(self, page: Page) -> int:
        try:
            links = page.locator(".paginator a").all()
            max_p = 1
            for link in links:
                text = link.inner_text().strip()
                href = link.get_attribute("href")

                # 数字があればそれをパース
                if text.isdigit():
                    max_p = max(max_p, int(text))
                # 数字でない場合（» 等）は href から取得を試みる
                elif href and "pag=" in href:
                    if match := re.search(r"pag=(\d+)", href):
                        max_p = max(max_p, int(match.group(1)))
            return max_p
        except Exception:
            pass
        return 1

    def scrape_listing(
            self,
            start_url: str,
            output_file: str,
            max_pages: int | None = None,
            delay: float = 1.0,
    ) -> dict:
        output_path = Path(output_file)
        scraped_urls = self._load_existing_urls(output_path)
        stats = {"total": 0, "new": 0, "skipped": 0, "errors": 0}

        context, page = browser_ini(
            str(self.DEFAULT_USER_DATA_DIR), headless=self.headless
        )

        try:
            page.goto(start_url, wait_until="domcontentloaded")
            time.sleep(delay * 2)

            if max_pages is None:
                max_pages = self._get_max_pages(page)
                print(f"最終ページ: {max_pages}")

            for page_num in range(1, max_pages + 1):
                if page_num > 1:
                    list_url = f"{start_url}?pag={page_num}"
                    print(f"\n=== ページ {page_num}: {list_url} ===")
                    page.goto(list_url, wait_until="domcontentloaded")
                    time.sleep(delay * 2)
                else:
                    list_url = start_url
                    print(f"\n=== ページ {page_num}: {list_url} ===")

                product_urls = self._collect_product_urls(page)
                print(f"  発見: {len(product_urls)} 件")
                stats["total"] += len(product_urls)

                for i, url in enumerate(product_urls, 1):
                    product_key = self._get_product_key(url)

                    # スキップ判定
                    if product_key in scraped_urls:
                        print(f"  [{i}/{len(product_urls)}] ⏭ スキップ")
                        stats["skipped"] += 1
                        continue

                    print(f"  [{i}/{len(product_urls)}] ⏳ {product_key}")

                    if product := self.scrape_product(page, url):
                        self._append_to_file(output_path, product)
                        scraped_urls.add(product_key)
                        print(f"    ✓ {product.brand} - {product.title[:25]}")
                        stats["new"] += 1
                    else:
                        stats["errors"] += 1

                    time.sleep(delay)

        except Exception as e:
            print(f"\nエラー: {e}")
            import traceback
            traceback.print_exc()
        finally:
            context.close()

        print(f"\n{'=' * 40}")
        print(f"総発見数: {stats['total']}")
        print(f"新規取得: {stats['new']}")
        print(f"スキップ: {stats['skipped']}")
        print(f"エラー:   {stats['errors']}")
        print(f"保存先:   {output_path}")
        print(f"{'=' * 40}")
        return stats


if __name__ == "__main__":
    scraper = GiglioScraper(headless=False)

    # 性別（is_women）に応じて取得URLを切り替え
    gender_path = "woman" if utils.is_women else "man"
    target_url = f"https://www.giglio.com/ja-jp/{gender_path}/shoes/"

    # 全ページを取得（utils.main_data を出力先に指定することでフォルダ構成と自動連動）
    scraper.scrape_listing(target_url, output_file=utils.main_data)
