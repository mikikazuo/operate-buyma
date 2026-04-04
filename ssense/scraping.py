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
            price_text = self._safe_get_text(page, '[data-test="pdpRegularPriceText"]')
            if match := re.search(r"¥([\d,]+)", price_text):
                return int(match.group(1).replace(",", ""))
        except Exception:
            pass
        return None

    def _extract_sizes(self, page: Page) -> list[str] | None:
        sizes, seen = [], set()
        try:
            for option in page.locator("#pdpSizeDropdown option").all():
                if option.get_attribute("disabled"):
                    continue
                text = option.inner_text()
                if text and text != "サイズの選択":
                    clean = re.sub(r"\s*-\s*残り\s*\d+", "", text).strip()
                    if clean and clean not in seen:
                        sizes.append(clean)
                        seen.add(clean)
        except Exception:
            pass
        return sizes if sizes else None

    def _extract_model_info(self, page: Page) -> str | None:
        try:
            for elem in page.locator(".pdp-product-description .s-text").all():
                text = elem.inner_text()
                if "モデル" in text or "身長" in text:
                    return text.strip()
        except Exception:
            pass
        return None

    def _extract_origin(self, page: Page) -> str | None:
        try:
            for elem in page.locator(".pdp-product-description p.s-text").all():
                text = elem.inner_text()
                if match := re.search(r"([^\s]+)\s*製", text):
                    return match.group(1) + "製"
        except Exception:
            pass
        return None

    def _extract_images(self, page: Page) -> list[str]:
        images = []
        try:
            for img in page.locator(".pdp-image img[data-srcset]").all():
                srcset = img.get_attribute("data-srcset")
                if srcset and "images/" in srcset:
                    full_url = srcset.split()[0]
                    path = parse.urlparse(full_url).path
                    if "images/" in path:
                        images.append(path.split("images/", 1)[1])
        except Exception:
            pass
        return images

    def _get_product_key(self, url: str) -> str:
        """URLから一意キーを抽出（スキップ判定用）"""
        return parse.urlparse(url).path.split("/", 4)[-1]

    def scrape_product(self, page: Page, url: str) -> ProductData | None:
        try:
            page.goto(url, wait_until="domcontentloaded")

            # 画像が読み込まれるまで少し待つ
            page.wait_for_timeout(2000)

            if self._extract_price(page) is None:
                return None

            url_parts = parse.urlparse(url).path.split("/")

            category_value = self._safe_get_attr(
                page, 'meta[property="product:category"]', "content"
            )
            category = [category_value] if category_value else None

            return ProductData(
                url=self._get_product_key(url),
                gender=url_parts[2] if len(url_parts) > 2 else None,
                category=category,
                brand=self._safe_get_text(page, "#pdpBrandNameText"),
                title=self._safe_get_text(page, "#pdpProductNameText"),
                product_code=self._safe_get_text(page, "#pdpProductSKUText"),
                price=self._extract_price(page),
                size=self._extract_sizes(page),
                model_info=self._extract_model_info(page),
                description=self._safe_get_text(
                    page, "#pdpProductDescriptionContainerText"
                ),
                material=self._safe_get_attr(
                    page, 'meta[property="product:material"]', "content"
                ),
                origin=self._extract_origin(page),
                img=self._extract_images(page),
            )
        except Exception as e:
            print(f"  ✗ エラー ({url}): {e}")
            return None

    def _collect_product_urls(self, page: Page) -> list[str]:
        urls = []
        for script in page.locator('script[type="application/ld+json"]').all():
            try:
                data = json.loads(script.inner_text())
                if "url" in data and "/product/" in data["url"]:
                    urls.append(f"{self.BASE_URL}{data['url']}")
            except Exception:
                continue
        return urls

    def _get_max_pages(self, page: Page) -> int:
        try:
            last_page_elem = page.locator("li.pagination__last-page a").first
            if last_page_elem.count() > 0:
                text = last_page_elem.inner_text().strip()
                return int(text)
        except Exception:
            pass
        return 1  # デフォルト

    def scrape_listing(
            self,
            start_url: str,
            output_file: str,
            max_pages: int | None = None,
            delay: float = 1.0,
    ) -> dict:
        """一覧ページから商品を収集してスクレイピング（都度保存・再開対応）"""
        output_path = Path(output_file)
        scraped_urls = self._load_existing_urls(output_path)
        stats = {"total": 0, "new": 0, "skipped": 0, "errors": 0}

        context, page = browser_ini(
            str(self.DEFAULT_USER_DATA_DIR), headless=self.headless
        )

        try:
            # 最初のページをロードして max_pages を取得
            page.goto(start_url, wait_until="domcontentloaded")
            time.sleep(delay * 2)
            if max_pages is None:
                max_pages = self._get_max_pages(page)
                print(f"最終ページ: {max_pages}")

            for page_num in range(1, max_pages + 1):
                if page_num > 1:
                    list_url = f"{start_url}?page={page_num}"
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
                    short_name = url.split("/")[-1][:35]

                    # スキップ判定
                    if product_key in scraped_urls:
                        print(f"  [{i}/{len(product_urls)}] ⏭ {short_name}")
                        stats["skipped"] += 1
                        continue

                    print(f"  [{i}/{len(product_urls)}] ⏳ {short_name}")

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
    scraper = SSenseScraper()

    scraper.scrape_listing("https://www.ssense.com/ja-jp/women",
                           output_file="women.json") if is_mikistyle else scraper.scrape_listing(
        "https://www.ssense.com/ja-jp/men", output_file="women.json" if is_mikistyle else "men.json")
