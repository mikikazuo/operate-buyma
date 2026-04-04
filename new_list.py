"""
Buyma出品RPA - Playwright版
"""

import sys
import time
import json
import unicodedata
import datetime
from dataclasses import dataclass, field
from typing import Optional
from concurrent.futures import ThreadPoolExecutor
from playwright.sync_api import (
    Page,
    Locator,
    TimeoutError as PlaywrightTimeout,
)

# 自作モジュール（パスは適宜調整）
import img_processing as imgPro
import google_translate as googleTra
import correctionDict as correct

import utils
from utils import make_price


# =============================================================================
# ユーティリティ関数
# =============================================================================


def get_east_asian_width_count(text: str) -> int:
    """東アジア文字幅を考慮した文字数カウント"""
    return sum(2 if unicodedata.east_asian_width(c) in "FWA" else 1 for c in text)


def is_japanese(string: str) -> bool:
    """日本語文字が含まれているか判定"""
    for ch in string:
        name = unicodedata.name(ch, "")
        if "CJK UNIFIED" in name or "HIRAGANA" in name or "KATAKANA" in name:
            return True
    return False


def get_description_text() -> str:
    """商品説明の定型文を取得"""
    return """

サイズ寸法についてお答えできる場合がございます。お気軽にお問い合わせください。


━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
　★お客様へのお願い
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ご注文後のキャンセルを防ぐため、お手数ではございますが
ご購入いただく前に在庫の確認をお願いいたします。
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
　★発送について
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
日本国内から宅配便にて発送いたします。
■ゆうパック送料込み（場合によってはクリックポスト）
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  ★ご注意事項
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
■買付について
　ご注文をいただいてからの買い付けとなりますので国内発送までに1週間〜、場合によっては2週間〜程お時間を頂きます。
　ご注文と同時に海外オーダーいたしますので、お取引途中でのキャンセルはできかねます。

■検品は十分行っておりますが、素材の質や縫製の質、細かな傷・汚れなど不良とまでは言えない程度の部分につきましては何卒ご容赦ください。

■お使いのPCモニタやスマートフォンの機種により色の見え方が多少異なる場合もございます。ご了承ください。

"""


def check_exhibition_limit(page: Page) -> bool:
    """出品制限数エラーページが表示されているかチェック"""
    try:
        error_element = page.locator(".fab-l-contents h1.ttl_1col").filter(
            has_text="出品制限数エラー"
        )
        error_element.wait_for(state="visible", timeout=5000)
        return True
    except PlaywrightTimeout:
        return False


def translate_title(category: list, title: str) -> str:
    """タイトルの一部を日本語化"""
    json_data = utils.load_json(utils.title_path)
    translate_dict = json_data.get(category[0], {})

    title_words = title.lower().split(" ")
    result = []

    for word in title_words:
        translated = translate_dict.get(word, "")
        if not translated and len(word) > 1 and word.endswith("s"):
            translated = translate_dict.get(word[:-1], "")
        result.append(translated if translated else word)

    # 日本語と英語を適切に連結
    modified = ""
    for word in result:
        if is_japanese(word):
            modified += word
        else:
            modified += " " + word

    return modified.strip()


# =============================================================================
# データクラス
# =============================================================================


@dataclass
class BuymaProductData:
    """Buyma出品商品データ"""

    product_name: str
    brand: str
    category: list
    price: int
    origin_price: float
    comments: str
    code: Optional[str] = None
    size_list: Optional[list[str]] = None
    imgs: list = field(default_factory=list)

    @classmethod
    def from_json(cls, data: dict) -> "BuymaProductData":
        """JSONデータからインスタンスを生成"""
        # 詳細情報の翻訳
        details = []
        detail_fields = [
            ("description", "説明"),
            ("heel", "ヒールの高さ"),
            ("color", "色"),
            ("material", "素材"),
            ("care", "取り扱い"),
            ("measure", "サイズ"),
            ("height", "高さ"),
            ("width", "幅"),
            ("depth", "奥行"),
            ("weight", "重量"),
            ("origin", "原産国"),
        ]

        for key, label in detail_fields:
            if key in data and data[key]:  # null/None/空文字を除外
                value = data[key]
                if key == "measure":
                    translated = googleTra.translate(value, False)
                elif key in ("height", "width", "depth", "weight"):
                    translated = value
                else:
                    translated = googleTra.translate(value)

                details.append(
                    f"{translated}" if utils.site == "giglio" and key == "description" else f"{label} : {translated}")

        comments = correct.correction("\n".join(details)) + get_description_text()
        # サイト固有の限定文言などを削除
        for site_name in ["ssense", "SSENSE", "giglio", "GIGLIO"]:
            comments = comments.replace(f"{site_name}だけの", "").replace(site_name, "")
        # カテゴリー解決
        category = cls._resolve_category(
            data["category"], correct.correction(data["title"])
        )

        # ブランド名
        brand = correct.correction(data["brand"])

        # 商品名（60文字以内に収める）
        raw_title = data["title"]
        for site_name in ["ssense", "SSENSE", "giglio", "GIGLIO"]:
            raw_title = raw_title.replace(site_name, "")

        raw_name = f"【{brand}】" + correct.correction(raw_title)
        product_name = raw_name
        for i in range(len(raw_name), 0, -1):
            if get_east_asian_width_count(raw_name[:i]) <= 60:
                product_name = raw_name[:i]
                break

        return cls(
            product_name=product_name,
            brand=brand,
            category=category,
            price=make_price(data["price"], utils.my_rate),
            origin_price=data.get("price", 0),
            comments=comments,
            code=(data.get("product_code") or data.get("code", ""))[:6] if (
                        data.get("product_code") or data.get("code")) else None,
            size_list=data.get("size"),
            imgs=data.get("img", []),
        )

    @staticmethod
    def _resolve_category(category_list: list, title: str) -> list:
        """カテゴリーを解決"""
        with open(utils.category_dict_path, encoding="utf-8") as f:
            json_data = json.load(f)
            category = json_data[f"depth{len(category_list)}"]

            for depth in category_list:
                category = category[depth]

            # タイトルからカテゴリー分類
            if isinstance(category, dict):
                title_words = [w.lower() for w in title.split()]
                result = category.get("other", [])

                for keyword, cat_value in category.items():
                    if keyword == "other":
                        continue
                    for word in title_words:
                        if keyword.lower() in (word, word.rstrip("s")):
                            result = cat_value
                            break
                category = result

            # 性別カテゴリーの追加
            if len(category) < 3:
                gender = (
                    "レディースファッション" if utils.is_women else "メンズファッション"
                )
                category = [gender] + category

        return category


# =============================================================================
# Buyma操作クラス
# =============================================================================


class BuymaExhibitor:
    """Buyma出品操作クラス"""

    def __init__(self, page: Page):
        self.page = page
        self.timeout = 60000  # 60秒

    def input_brand(self, brand: str) -> bool:
        """ブランド入力"""
        brand_data = utils.load_json(utils.brand_path)

        if brand not in brand_data:
            raise Exception("Brand not in dictionary")

        brand_name = brand_data[brand]
        if not brand_name:
            raise Exception("Brand not found in Buyma")

        text_fields = self.page.locator(".bmm-c-text-field")
        text_fields.nth(1).fill(brand_name)

        # ブランド候補を待機してクリック
        suggest = self.page.locator(".bmm-c-suggest__main").first
        suggest.wait_for(state="visible", timeout=self.timeout)
        suggest.click()

        return True

    def input_text_fields(self, data: BuymaProductData):
        """テキストフィールド入力"""
        fields = self.page.locator(".bmm-c-text-field")

        fields.nth(0).fill(data.product_name)
        if data.code:
            fields.nth(3).fill(data.code)
        fields.nth(7).fill(str(data.price))

    def input_text_area(self, data: BuymaProductData):
        """テキストエリア入力"""
        areas = self.page.locator(".bmm-c-textarea")
        areas.nth(0).fill(data.comments)

    def input_category(self, category: list):
        """カテゴリー入力"""
        print(f"Category: {category}")

        for i, cat in enumerate(category):
            genre = self.page.locator(".Select-multi-value-wrapper").nth(i)
            genre.click()

            self.page.locator(".Select-menu-outer").wait_for(state="visible")

            option = self.page.locator(f'[aria-label="{cat}"]')
            option.click()

    def input_size(self, data: BuymaProductData):
        """サイズ入力"""
        self.page.locator("#react-tabs-2").click()
        time.sleep(0.5)
        self.page.locator(".Select-placeholder").last.wait_for(state="visible")
        self.page.locator(".Select-placeholder").last.click()
        time.sleep(0.5)

        size_panel = self.page.locator(".bmm-c-panel__item").nth(-14)

        if not data.size_list or data.size_list[0] == utils.one_size_name:
            # ワンサイズ
            self.page.locator('[aria-label="バリエーションなし"]').click()
        else:
            # 複数サイズ
            self.page.locator('[aria-label="バリエーションあり"]').click()
            for i, size in enumerate(data.size_list):
                if i > 0:
                    size_panel.locator(".bmm-c-form-table__foot a").filter(
                        has_text="新しいサイズを追加"
                    ).click()

                self._wait_for_select_controls(size_panel, 3 + i)
                size_panel.locator(".Select-control").nth(2 + i).click()
                self.page.locator('[aria-label="指定なし"]').click()
                size_panel.locator('[type="text"]').nth(i).fill(size.replace("˝", ""))

        # 数量
        self.page.locator(".sell-amount-input input").fill("2")

    def _wait_for_select_controls(self, panel: Locator, count: int):
        """Select要素が指定数になるまで待機"""
        for _ in range(100):
            if panel.locator(".Select-control").count() >= count:
                return
            time.sleep(0.1)

    def upload_images(self, img_urls: list, success_count: int, batch_num: int):
        """画像アップロード"""
        for i in range(success_count):
            imgPro.imgEditOne(i, success_count, batch_num)
            img_path = f"{utils.img_dir}{i + 1}.jpg"

            if i == 0:
                self.page.locator(".bmm-c-img-upload").wait_for(state="visible")
            else:
                self.page.locator(".bmm-c-img-upload__dropzone-plus").wait_for(
                    state="visible"
                )

            self.page.locator(".bmm-c-img-upload input").set_input_files(img_path)

    def submit(self):
        """出品確定"""
        self.page.locator(".bmm-c-img-upload__dropzone-plus").wait_for(
            state="visible", timeout=self.timeout
        )
        self.page.locator(".bmm-c-btn").last.click()
        # ボタンが4つになるまで待機
        for _ in range(600):
            if self.page.locator(".bmm-c-btn").count() >= 4:
                break
            time.sleep(0.1)
        self.page.locator(".bmm-c-btn").last.click()

        # 完了ページまで待機
        self.page.wait_for_url(
            "https://www.buyma.com/my/sell/completed", timeout=self.timeout
        )


# =============================================================================
# フィルタリング関数
# =============================================================================


def should_skip_product(data: dict, uploaded_urls: set) -> bool:
    """商品をスキップすべきか判定"""
    # 性別チェック（"men", "メンズ", "women", "レディース" に対応）
    allowed_genders = ("women", "レディース") if utils.is_women else ("men", "メンズ")
    if data["gender"] not in allowed_genders:
        return True

    # 価格上限チェック
    if data["price"] >= utils.over_price:
        return True

    # カテゴリーチェック
    if _is_excluded_category(data):
        return True

    # ブランドチェック
    if _is_excluded_brand(data):
        return True

    # 既にアップロード済み
    if data["url"] in uploaded_urls:
        return True

    # サイズの重複チェック
    if "size" in data and isinstance(data["size"], list):
        if len(data["size"]) != len(set(data["size"])):
            return True

        # サイズ名の文字数チェック（全角13文字・半角26文字以内）
        for size in data["size"]:
            if get_east_asian_width_count(size) > 26:
                return True

    # 除外ブランド
    title_lower = data.get("title", "").lower()
    if "converse" in title_lower or "harrington" in title_lower:
        return True

    return False


def _is_excluded_category(data: dict) -> bool:
    """除外カテゴリーか判定"""
    json_data = utils.load_json(utils.category_dict_path)
    category = json_data[f'depth{len(data["category"])}']

    for depth in data["category"]:
        category = category[depth]

    if isinstance(category, dict):
        category = category.get("other", [])

    if isinstance(category, list):
        if not category:
            return True
        for pass_cat in utils.pass_category_list:
            if pass_cat in category:
                return utils.is_pass

    return not utils.is_pass


def _is_excluded_brand(data: dict) -> bool:
    """除外ブランドか判定"""
    brand = correct.correction(data["brand"]).lower()

    brand_data = utils.load_json(utils.brand_path)
    return brand_data.get(brand) is None


# =============================================================================
# メイン処理
# =============================================================================


def save_upload_data(page: Page, url: str, price: int, size_list: Optional[list]):
    """アップロードデータを保存"""
    upload_data = utils.load_json(utils.upload_data) or []

    link = page.locator(".sell-complete__lead a")
    href = link.get_attribute("href") or ""
    up_url = href.split("/")[-1]

    now = datetime.datetime.now()
    new_entry = {
        "url": url,
        "upurl": up_url,
        "price": price,
        "size": size_list,
        "date": [now.year, now.month, now.day],
        "exhibited": True,
    }
    print(new_entry)
    upload_data.append(new_entry)

    utils.save_json(upload_data, utils.upload_data)


def process_products(page: Page):
    """商品処理メイン"""
    # データ読み込み
    products = utils.load_json(utils.main_data) or []
    uploaded = utils.load_json(utils.upload_data) or []
    uploaded_urls = {item["url"] for item in uploaded if item["exhibited"]}

    # フィルタリング
    valid_products = [
        {"data": p, "line": i}
        for i, p in enumerate(products)
        if i >= utils.start_index - 2 and not should_skip_product(p, uploaded_urls)
    ]

    exhibitor = BuymaExhibitor(page)

    # 画像の事前取得（並列）
    pending_results = []
    with ThreadPoolExecutor(max_workers=utils.get_img_num) as executor:
        futures = []
        for i, item in enumerate(valid_products[: utils.get_img_num - 1]):
            future = executor.submit(imgPro.download_Allimg, item["data"]["img"], i + 1)
            futures.append(future)

        for future in futures:
            pending_results.append(future.result())

    for idx, item in enumerate(valid_products):
        data = item["data"]
        line = item["line"]

        print(f"Line No: {line + 2}   URL: {data['url']}")

        # 画像取得結果
        if pending_results:
            success_count = pending_results.pop(0)
        else:
            success_count = 0

        # 次の画像を事前取得
        next_idx = idx + utils.get_img_num - 1
        if next_idx < len(valid_products):
            with ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(
                    imgPro.download_Allimg,
                    valid_products[next_idx]["data"]["img"],
                    (next_idx % utils.get_img_num) + 1,
                )
                pending_results.append(future.result())

        if success_count == 0:
            print("No images - skipping")
            continue

        product = BuymaProductData.from_json(data)

        # サイズ上限チェック
        if product.size_list:
            if len(product.size_list) > 20:
                continue

        # リトライループ
        max_retries = 3
        for attempt in range(max_retries):
            try:
                page.goto(utils.up_url)
                if check_exhibition_limit(page):
                    print("出品制限数エラー: 出品中の商品数が制限を超えています。")
                    sys.exit(1)
                page.locator(".bmm-c-panel__item").first.wait_for(state="visible")

                # フォーム入力
                exhibitor.input_brand(product.brand.lower())
                exhibitor.input_text_fields(product)
                exhibitor.input_text_area(product)
                exhibitor.input_category(product.category)
                exhibitor.input_size(product)

                # 画像アップロード
                exhibitor.upload_images(
                    data["img"], success_count, idx % utils.get_img_num + 1
                )

                # 出品確定
                exhibitor.submit()
                break

            except PlaywrightTimeout:
                print(f"Timeout - retry {attempt + 1}/{max_retries}")
            except Exception as e:
                print(f"Error: {e} - retry {attempt + 1}/{max_retries}")
        else:
            print(f"Failed after {max_retries} retries")
            continue

        print("Finished\n")
        save_upload_data(page, data["url"], product.price, product.size_list)


def checker():
    """デバッグ用 - 条件に合う商品数を表示"""
    products = utils.load_json(utils.main_data) or []
    uploaded = utils.load_json(utils.upload_data) or []
    uploaded_urls = {item["url"] for item in uploaded if item["exhibited"]}

    count = 0
    max_price = 0

    for p in products:
        if should_skip_product(p, uploaded_urls):
            continue
        count += 1
        max_price = max(max_price, p["price"])

    print(f"Product Count: {count}")
    print(f"Price Max: {max_price}")


if __name__ == "__main__":
    """メインエントリーポイント"""
    context, page = utils.browser_ini(utils.user_data_dir)
    if utils.is_check:
        checker()
    else:
        process_products(page)

    context.close()
