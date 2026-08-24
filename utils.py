from playwright.sync_api import sync_playwright
import atexit
import json
import os
from collections import OrderedDict

img_dir = r".\img\madeimg"
# google翻訳のキャッシュ
translate_path = "json/twoFour_detail_dict.json"

# 対象サイト ("ssense" or "giglio")
site = "ssense"

# mikistyleかどうか
is_mikistyle = is_women = True


# サイズがない場合の　特定ワード
one_size_name = "one size one size"

# BUYMAユーザーデータディレクトリ
user_data_dir = "./user_data/miki" + ("style" if is_mikistyle else "store")

# buyma出品で記述するブランド名管理
brand_path = "./data/brand.json"

# 除外検索するときはtrue  該当検索するときはfalse
is_pass = True

# サイト・性別ごとの設定
# 性別に基づいたファイル名の接頭辞
gender_prefix = "women" if is_women else "men"

category_dict_path = f"{site}/{gender_prefix}_category.json"

# サイトごとのフォルダ構成に基づいたパス生成
if site == "giglio":
    img_url = ""
    product_url = "https://www.giglio.com/ja-jp/"
    # giglio の場合は男女ともに _shoes という接尾辞が付く
    main_data = f"{site}/{gender_prefix}.json"
    upload_data = f"{site}/{gender_prefix}_upload.json"
else:
    img_url = "https://img.ssensemedia.com/images/"
    product_url = "https://www.ssense.com/ja-jp/men/product/"
    main_data = f"{site}/{gender_prefix}.json"
    upload_data = f"{site}/{gender_prefix}_upload.json"


if is_women:
    up_url = "https://www.buyma.com/my/sell/new?copy_id=126842091&tab=b"
    pass_category_list = [
        "キャンドル",
        "サングラス",
        "アウター",
        "スウェット・トレーナー",
        # "Tシャツ・カットソー",
        # "ショートパンツ",
        "ニット・セーター",
        "ライフスタイル" "スーツケース",
    ]
else:
    up_url = "https://www.buyma.com/my/sell/new?copy_id=103628319&tab=b"
    # pass_category_list = [
    #     "キャンドル",
    #     "水着",
    #     "サンダル",
    #     "ハーフ・ショートパンツ",
    #     "ポロシャツ",
    #     "Tシャツ・カットソー",
    # ]
    pass_category_list = [
        "スウェット・トレーナー",
        "ニット・セーター",
        "アウター・ジャケット"
    ]

# 除外ブランド（小文字で登録）
pass_brands = {"converse", "dior", "acne studios", "dolce & gabbana", "barbour"}

# 商品のタイトルキーワードの翻訳
title_path = "json/titleDict.json"

# 商品データのどこから開始するかを行で表す
start_index = 0

# updateStack のupdatePrice時　レートを低く設定する必要あり
my_rate = 1.2 * 1.077

discount_min_rate = 1.1

# これより大きい金額は除外
over_price = 150000

# マルチスレッド時にダウンロードする画像数
get_img_num = 5

# 事前検索かどうか
is_check = False


def browser_ini(login_data_path, headless=False):
    """
    Playwrightでブラウザを初期化
    ログイン済みのユーザーデータを使用

    Args:
        login_data_path: ユーザーデータディレクトリのパス
        headless: ヘッドレスモードで起動するか (デフォルト: False)

    Returns:
        tuple: (context, page)
    """
    playwright = sync_playwright().start()
    # スクリプト終了時に自動的にplaywrightを停止
    atexit.register(playwright.stop)

    # 相対パスを絶対パスに変換（Playwrightは絶対パスが必要）
    abs_user_data_dir = os.path.abspath(login_data_path)
    print(f"✓ user-data-dir を読込: {abs_user_data_dir}")

    # persistent_context を使用してユーザーデータを引き継ぐ
    context = playwright.chromium.launch_persistent_context(
        user_data_dir=abs_user_data_dir,
        headless=headless,
        channel="chrome",  # システムのChromeを使う場合はコメント解除
        args=[
            "--disable-blink-features=AutomationControlled",
            "--disable-web-security",
            "--disable-features=VizDisplayCompositor",
        ],
    )

    # 最初のページを取得、なければ新規作成
    page = context.pages[0] if context.pages else context.new_page()

    # BOT検知回避のためのスクリプト
    page.add_init_script(
        """
        Object.defineProperty(navigator, 'webdriver', {
            get: () => undefined,
        });
    """
    )

    return context, page


def load_json(file_path):
    """JSONファイルを読み込み、存在しない場合は空のOrderedDictを返す"""
    try:
        with open(file_path, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        # ディレクトリが存在しない場合は作成
        dir_path = os.path.dirname(file_path)
        if dir_path and not os.path.exists(dir_path):
            os.makedirs(dir_path)
        return OrderedDict()
    except json.JSONDecodeError as e:
        print(f"Error: Failed to decode JSON from {file_path}: {e}")
        raise


def save_json(data, file_path):
    """JSONデータをファイルに保存"""
    try:
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"Error: Failed to save JSON to {file_path}: {e}")
        raise


def make_clear_price(price: float) -> int:
    """価格を見やすい数値に丸める"""
    main_price = price / 10000
    clear_price = int(main_price) * 10000
    if main_price != 0:
        sub_price = price % 10000
        clear_price += 9800 if sub_price > 5000 else 4980
    return int(clear_price)


def make_price(price: float, rate: float) -> int:
    """販売価格を計算"""
    export_border = 60000
    export_price = 4000

    tax_price = price * rate
    if price < export_border:
        tax_price += export_price
    tax_price += 1500

    return make_clear_price(tax_price)
