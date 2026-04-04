import re
import utils
import correctionDict as correct

# ブランド入力欄のセレクタ
BRAND_INPUT_SELECTOR = ".bmm-c-suggest__input input.bmm-c-text-field"
# サジェストリストのセレクタ
SUGGEST_SELECTOR = ".bmm-c-suggest__main"


def make_brand_dict():
    """ブランド辞書を作成するメイン関数"""

    # 既存のブランドデータを読み込み
    brand_json_datas = utils.load_json(utils.brand_path)

    # 除外ブランドに設定された既存ブランドをNoneに更新
    updated = False
    for brand in utils.pass_brands:
        if brand_json_datas.get(brand) is not None:
            brand_json_datas[brand] = None
            print(f"除外ブランドに設定されたため、{brand} を None に更新")
            updated = True
    if updated:
        utils.save_json(brand_json_datas, utils.brand_path)

    # ブランドリストの作成（除外ブランド・登録済みブランドをフィルタリング）
    json_data = utils.load_json(utils.main_data) or []
    lower_brand_list = [correct.correction(data["brand"]).lower() for data in json_data]
    brand_list = [
        brand
        for brand in lower_brand_list
        if (brand not in utils.pass_brands and brand_json_datas.get(brand) is None)
    ]
    # 重複を除去（順序を保持）
    brand_list = list(dict.fromkeys(brand_list))

    if not brand_list:
        print("処理対象のブランドがありません")
        return

    print(f"処理対象: {len(brand_list)}件")

    context, page = utils.browser_ini(utils.user_data_dir)

    try:
        page.goto(utils.up_url)

        for brand in brand_list:
            # ブランド検索
            result = find_brand(page, brand)
            brand_json_datas[brand] = result
            utils.save_json(brand_json_datas, utils.brand_path)
            print(
                f"✓ {brand} -> {result}" if result else f"✗ {brand} -> 見つかりません"
            )

    finally:
        context.close()


def find_brand(page, brand):
    """
    ブランド名を徐々に単語数を減らしながら候補を検索

    Returns:
        str or None: 見つかったブランド名、見つからなければNone
    """
    # ブランド入力欄を取得
    brand_input = page.locator(BRAND_INPUT_SELECTOR)
    brand_word_list = brand.split(" ")

    for i in range(len(brand_word_list), 0, -1):
        brand_words = " ".join(brand_word_list[:i])
        brand_input.fill(brand_words)

        # サジェストが表示されるまで少し待機
        page.wait_for_timeout(1000)

        # サジェストが表示されているかチェック
        suggest_items = page.locator(SUGGEST_SELECTOR)
        if suggest_items.count() == 0:
            continue

        # サジェストの1番目を取得
        suggest_text = suggest_items.first.text_content()

        # 比較用に正規化（括弧内削除、小文字化、空白削除）
        cleaned_suggest = re.sub(r"\(.*\)", "", suggest_text).lower().replace(" ", "")
        cleaned_brand = brand_words.replace(" ", "")

        if cleaned_suggest == cleaned_brand:
            return brand_words

    return None


if __name__ == "__main__":
    make_brand_dict()
