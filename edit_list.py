import time
from utils import browser_ini
import utils
import datetime
from utils import make_price


class PageMode:
    """
    対象ページ
    """

    # 出品中
    Listing = "for_sale"
    # リクエスト中
    Request = "accepting_requests"
    # 出品停止中
    Stopping = "suspended"


class Bot:
    page_mode = PageMode.Listing

    def __init__(self):
        self.context, self.page = browser_ini(utils.user_data_dir)
        self.url = f"https://www.buyma.com/my/sell/?status={Bot.page_mode}"

    def driver_wait(self, selector):
        """
        要素表示までの待機
        """
        self.page.wait_for_selector(selector, timeout=20000)

    def check_not_found_error(self):
        """
        エラー通知「お客様がお探しのページは見つかりませんでした。」が表示されているかチェック。
        """
        if self.page.locator(".error_box .message_error").count() > 0:
            msg = self.page.locator(".error_box .message_error").first.text_content()
            if "見つかりませんでした" in msg:
                return True
        return False

    def all_select_temp(self):
        """
        ある１ページの全商品を選択
        """
        # 表示件数を100にする
        self.page.select_option(".js-row-count-options", "100")

        # すべての商品の選択 (ON -> OFF -> ONで確実につける)
        self.page.click(".js-checkbox-check-all")
        time.sleep(1)
        self.page.click(".js-checkbox-check-all")
        time.sleep(1)
        self.page.click(".js-checkbox-check-all")

        self.page.click(".my_action_output")

    def update_deadline(self, deadline):
        """
        購入期限の更新
        :param deadline: 購入期限
        """
        for i in range(51):
            self.page.goto(
                f"https://www.buyma.com/my/sell/?status={PageMode.Request}"
                + (f"&page={i + 1}" if Bot.page_mode == PageMode.Listing else "")
            )

            self.all_select_temp()

            # 編集
            self.page.click(".js-chk-edit-checked")
            try:
                # 出品停止の場合用に、出品中に変更
                self.page.click("#rdoSyupinStatus1")
            except Exception:
                print("商品無し")
                raise Exception
            # 期限の変更フォーム
            self.page.click("#rdoYukodateEditKbn1")
            self.page.fill(".hasDatepicker", deadline)
            # 決定
            self.page.click("#confirmButton")
            # 再確認
            self.driver_wait("#completeButton")
            self.page.click("#completeButton")
            print(f"ページ {i + 1} を更新")

    def update_none_stock(self, category=None):
        """
        在庫なし商品の出品停止
        メインデータに存在しないURL（削除された商品）をBUYMAから削除
        :param category: カテゴリの指定（一部一致）
        """
        import re
        
        # メインデータ（スクレイピング元の最新データ）を読み込む
        main_data_list = utils.load_json(utils.main_data) or []
        # アップロードデータ（BUYMA出品済みデータ）を読み込む
        upload_data_list = utils.load_json(utils.upload_data) or []

        # メインデータのURLリストを作成
        main_data_url_list = [data["url"] for data in main_data_list]

        print("==== 在庫なし商品の削除 ====")
        print(f"アップロード総数 : {len(upload_data_list)}")
        print(f"取得データ総数 : {len(main_data_list)}")

        # 保持すべき商品番号のリスト（main_dataに存在し、かつexhibitedがTrueのもののみ）
        keep_upurl_list = []
        upload_modify_list = []
        for upload in upload_data_list:
            if upload["url"] in main_data_url_list and upload.get("exhibited", False):
                keep_upurl_list.append(upload["upurl"])
            upload_modify_list.append(upload)

        print(f"保持対象商品数 : {len(keep_upurl_list)}")

        if len(keep_upurl_list) == 0:
            print("パス設定ミス：保持対象が0件")
            return

        deleted_count = 0  # 削除された商品数

        current_url = self.url
        
        # ページネーションを取得するために、まずは一覧画面(1ページ目)を開く
        self.page.goto(current_url)
        time.sleep(5)

        if category:
            # フィルタ設定
            self.page.locator(".Select-multi-value-wrapper").first.click()
            time.sleep(1)
            self.page.locator(f'.Select-option[aria-label*="{category}"]').first.click()
            time.sleep(1)
            self.page.locator(".bmm-c-input-panel__button-search").click()
            time.sleep(5)
            current_url = self.page.url
            # ハッシュ(#)が含まれている場合は除去する
            current_url = current_url.split('#')[0]
            current_url = re.sub(r'([?&])page=\d+', r'\1', current_url)

        # 最後のページ番号を取得
        max_page = 1
        last_btn = self.page.locator('.paging a.box:has-text("最後")')
        if last_btn.count() > 0:
            href = last_btn.first.get_attribute("href")
            if href:
                m = re.search(r'page=(\d+)', href)
                if m:
                    max_page = int(m.group(1))
        else:
            # 「最後」ボタンがない場合は、表示されているページ番号から最大値を取得
            pages = self.page.locator(".paging .page").all_text_contents()
            valid_pages = [int(p.strip()) for p in pages if p.strip().isdigit()]
            if valid_pages:
                max_page = max(valid_pages)

        print(f"最大ページ数 : {max_page}")

        # ページを逆順で処理
        for i in reversed(range(max_page)):
            print(f"ページ : {i + 1}")

            sep = "" if current_url.endswith("?") or current_url.endswith("&") else ("&" if "?" in current_url else "?")
            # 出品中の商品一覧ページに移動
            self.page.goto(current_url + sep + f"page={i + 1}")
            time.sleep(5)
            # すべてのチェックボックスを取得
            checkboxes = self.page.locator("td.fab-checkbox-wrap input").all()

            checked = False
            for checkbox in checkboxes:
                value = checkbox.get_attribute("value")
                # 保持リストに含まれていないものを削除対象とする
                if value and value not in keep_upurl_list:
                    print(f"削除対象 : {value}")
                    checkbox.click()
                    checked = True
                    deleted_count += 1

            # チェックされた商品があれば削除処理
            if checked:
                self.page.click(".my_action_output")
                self.page.click(".js-chk-del-checked")
                try:
                    # 削除確認ボタンをクリック
                    self.page.click("#delete")
                except Exception:
                    pass

        print(f"削除した商品数 : {deleted_count}")
        # 更新されたアップロードデータを保存
        utils.save_json(upload_modify_list, utils.upload_data)

    def increase_price(self):
        """
        値上げ（割引後も含む）
        """
        main_data_list = utils.load_json(utils.main_data) or []

        upload_data_list = utils.load_json(utils.upload_data) or []
        upload_data_list = [item for item in upload_data_list if item["exhibited"]]

        # 更新対象のリストを作成
        target_updates = []
        for item in upload_data_list:
            for new_item in main_data_list:
                if new_item["url"] == item["url"]:
                    old_price = item["price"]
                    new_price = make_price(new_item["price"], utils.my_rate)
                    if old_price < new_price:
                        target_updates.append(
                            {
                                "url": item["url"],
                                "upurl": item["upurl"],
                                "old_price": old_price,
                                "new_price": new_price,
                            }
                        )
                    break

        print(f"更新対象数 : {len(target_updates)}")

        upload_modify_list = utils.load_json(utils.upload_data) or []

        print("==== 価格上昇 ====")
        for target in target_updates:
            print(
                f"URL : {target['url']}   商品番号 : {target['upurl']}   旧価格 : {target['old_price']}   新価格 : {target['new_price']}"
            )
            self.page.goto(
                f"https://www.buyma.com/my/sell/{target['upurl']}/edit?tab=b"
            )

            if self.check_not_found_error():
                print(f"エラー: ページが見つかりません。出品状態をFalseに更新します ({target['url']})")
                for modify in upload_modify_list:
                    if modify["url"] == target["url"]:
                        modify["exhibited"] = False
                        break
                utils.save_json(upload_modify_list, utils.upload_data)
                continue

            self.driver_wait(".bmm-c-text-field")
            text_field = self.page.locator(".bmm-c-text-field")
            fields = text_field.all()
            fields[-4].click()
            fields[-4].fill(str(target["new_price"]))
            self.page.locator(".bmm-c-btn").last.click()
            self.page.wait_for_url("https://www.buyma.com/my/sell/completed")

            for modify in upload_modify_list:
                if modify["url"] == target["url"]:
                    modify["price"] = target["new_price"]
                    modify["date"] = datetime.datetime.now().strftime("%Y-%m-%d")
                    break

            utils.save_json(upload_modify_list, utils.upload_data)

    def discount_price(self, discount_percent, is_price_up=False):
        """
        パーセントベースの価格変更
        :param discount_percent: 率
        :param is_price_up: 値上げかどうか
        """
        # メインデータ（スクレイピング元の最新データ）を読み込む
        main_data_list = utils.load_json(utils.main_data) or []
        # アップロードデータ（BUYMA出品済みデータ）を読み込む
        upload_data_list = utils.load_json(utils.upload_data) or []
        upload_data_list = [item for item in upload_data_list if item["exhibited"]]

        print("==== 割引処理 ====")
        target_upurl = []  # 割引対象のBUYMA商品番号リスト
        for upload in upload_data_list:
            if not upload.get("date"):
                continue
            # 出品日をdatetimeオブジェクトに変換
            if isinstance(upload["date"], list):
                date_obj = datetime.datetime(*upload["date"])
            else:
                date_obj = datetime.datetime.strptime(upload["date"], "%Y-%m-%d")
            # 出品日から14日以上経過
            days = (datetime.datetime.now() - date_obj).days
            if days < 14:
                continue
            # 対応するメインデータの価格を取得
            main_price = None
            for main in main_data_list:
                if main["url"] == upload["url"]:
                    main_price = main["price"]
                    break
            if main_price is None:
                continue
            # 指定％値引き後の価格が make_price の価格より上
            discounted_price = upload["price"] * (1 - discount_percent / 100)
            if discounted_price > main_price * utils.discount_min_rate:
                target_upurl.append(upload["upurl"])

        print(f"割引対象数 : {len(target_upurl)}")

        if not target_upurl:
            print("対象なし")
            return

        # ページを処理
        for i in range(51):
            print(f"ページ : {i + 1}")

            # 出品中の商品一覧ページに移動
            self.page.goto(self.url + f"&page={i + 1}")

            # すべてのチェックボックスを取得
            checkboxes = self.page.locator("td.fab-checkbox-wrap input").all()

            checked = False
            checked_upurls = []
            for checkbox in checkboxes:
                value = checkbox.get_attribute("value")
                if value in target_upurl:
                    print(f"割引対象 : {value}")
                    checkbox.click()
                    checked = True
                    checked_upurls.append(value)

            # チェックされた商品があれば割引処理
            if checked:
                self.page.click(".my_action_output")
                self.page.click(".js-chk-edit-checked")
                # デフォルトは値下げ
                self.page.click("#rdoPriceEditKbn1")
                if is_price_up:  # 値上げ
                    self.page.click("#lstPriceEditStyle")
                    self.page.locator("#lstPriceEditStyle option").nth(2).click()
                self.page.fill("input[name='txtPriceEdit']", str(discount_percent))
                # 決定
                self.page.click("#confirmButton")
                # 再確認
                self.driver_wait("#completeButton")
                self.page.click("#completeButton")
                print(f"割引ページ {i + 1} 完了")

                # 割引後のデータを更新
                upload_modify_list = utils.load_json(utils.upload_data) or []
                for upload in upload_modify_list:
                    if upload["upurl"] in checked_upurls:
                        discounted_price = upload["price"] * (
                            1 - discount_percent / 100
                        )
                        upload["price"] = int(discounted_price)
                        upload["date"] = datetime.datetime.now().strftime("%Y-%m-%d")
                utils.save_json(upload_modify_list, utils.upload_data)

    def update_size(self):
        """
        サイズバリエーションの変更
        """

        # サイズ名を正規化（「˝ 」を削除）
        def normalize_size(size):
            if isinstance(size, str):
                return size.replace("˝ ", "")
            return size

        # 新たにサイズを加える
        def add_size(new_size_list):
            change_flag = False
            sizes = self.page.locator(
                ".sell-stock-table__head-row td:nth-child(2), .sell-stock-table__rest-row td:nth-child(2)"
            ).all_text_contents()
            self.page.locator("#react-tabs-2").click()
            for new_size in new_size_list:
                if new_size not in sizes:
                    # 前の部分でクリックしてしまうと、urlスキップ時アラートが発生するためここに移動
                    self.page.click("text=新しいサイズを追加")
                    size_position = self.page.locator(".react-tabs")
                    size_position.locator(".Select-control").last.click()
                    self.page.locator('[aria-label="指定なし"]').click()
                    size_position.locator('[type="text"]').last.fill(new_size)
                    change_flag = True
            # ドラッグ移動でサイズ順を変更しようとすると、重複サイズが発生するため保留
            return change_flag

        # 既存のBUYMA登録サイズに対する更新
        def update_size_stock(new_size_list):
            def change_state(from_state, to_state, should_include):
                """
                サイズの状態を変更
                :param from_state: 変更前の状態
                :param to_state: 変更後の状態
                :param should_include: Trueなら new_size_list に含まれるものを変更、Falseなら含まれないものを変更
                :return: 変更があったかどうか
                """
                flag = False
                for index, size in enumerate(sizes):
                    is_in_list = size in new_size_list
                    if is_in_list == should_include:
                        state = self.page.locator(
                            ".sell-stock-table__head-row .Select-control, .sell-stock-table__rest-row .Select-control"
                        ).nth(index)
                        state_text = state.text_content()
                        if state_text == from_state:
                            state.click()
                            self.page.locator(
                                f'.Select-option:has-text("{to_state}")'
                            ).click()
                            flag = True
                return flag

            sizes = self.page.locator(
                ".sell-stock-table__head-row td:nth-child(2), .sell-stock-table__rest-row td:nth-child(2)"
            ).all_text_contents()

            # まず、買付可にする処理（すべてが在庫なしになると在庫数が強制的に空になって再入力が必要となるため）
            changed1 = change_state("在庫なし", "買付可", True)
            # 次に、在庫なしにする処理
            changed2 = change_state("買付可", "在庫なし", False)

            return changed1 or changed2

        main_data_list = utils.load_json(utils.main_data) or []
        upload_data_list = utils.load_json(utils.upload_data) or []
        upload_data = [
            upload
            for upload in upload_data_list
            if upload["exhibited"] and upload["size"]
        ]

        # 更新対象のリストを作成
        target_updates = []
        for upload in upload_data:
            for new_data in main_data_list:
                # new_data["size"]がNoneの場合はスキップ
                if not new_data.get("size"):
                    continue
                # new_data["size"]はリストなので、各要素を正規化
                new_size = [normalize_size(s) for s in new_data["size"]]
                # サイズのリストが違う 何らかの更新が必要
                if new_data["url"] == upload["url"] and new_size != upload["size"]:
                    target_updates.append(
                        {
                            "url": upload["url"],
                            "upurl": upload["upurl"],
                            "new_size": new_size,
                        }
                    )
                    break

        print(f"更新対象 : {len(target_updates)}")

        upload_edited_data = upload_data_list.copy()

        for target in target_updates:
            print(
                f"url : {target['url']}   upurl : {target['upurl']}    size : {','.join(target['new_size'])}"
            )
            self.page.goto(
                f"https://www.buyma.com/my/sell/{target['upurl']}/edit?tab=b"
            )

            if self.check_not_found_error():
                print(f"エラー: ページが見つかりません。出品状態をFalseに更新します ({target['url']})")
                for item in upload_edited_data:
                    if item["url"] == target["url"]:
                        item["exhibited"] = False
                        break
                utils.save_json(upload_edited_data, utils.upload_data)
                continue

            # URLに「buyeritemdetail」が含まれる場合はスキップして削除
            current_url = self.page.url
            if "buyeritemdetail" in current_url:
                print(f"buyeritemdetailが含まれるためスキップ: {current_url}")
                # upload_edited_dataから削除
                upload_edited_data = [
                    item for item in upload_edited_data if item["url"] != target["url"]
                ]
                utils.save_json(upload_edited_data, utils.upload_data)
                continue

            self.driver_wait(".bmm-c-text-field")

            # この順番　すべてのサイズが在庫なしに選択されると　買い付け合計数量の欄が空になり、再設定が必要になるため
            added = add_size(target["new_size"])
            updated = update_size_stock(target["new_size"])
            if added or updated:
                print("変更")
                self.page.locator(".bmm-c-btn").last.click()
                self.page.wait_for_url("https://www.buyma.com/my/sell/completed")

                for modify in upload_edited_data:
                    if modify["url"] == target["url"]:
                        modify["size"] = target["new_size"]
                        break
                utils.save_json(upload_edited_data, utils.upload_data)
            else:
                print("変更なし")

    def set_unexhibited(self, count):
        """
        アップロードデータの先頭から指定個数の商品を出品停止（exhibited=False）にする
        :param count: 先頭から停止する商品数
        """
        upload_data_list = utils.load_json(utils.upload_data) or []

        print(f"==== 出品停止処理 ====")
        print(f"アップロード総数 : {len(upload_data_list)}")

        changed_count = 0
        for item in upload_data_list[:count]:
            if item.get("exhibited", False):
                item["exhibited"] = False
                changed_count += 1
                print(f"停止 : {item['url']}  商品番号 : {item['upurl']}")

        print(f"停止した商品数 : {changed_count}")
        utils.save_json(upload_data_list, utils.upload_data)

    def delete(self):
        for i in range(60):
            self.page.goto(self.url)

            self.all_select_temp()
            # 削除
            self.page.click(".js-chk-del-checked")
            try:
                # 決定
                self.page.click("#delete")
            except Exception:
                print("商品無し")
                raise Exception
            print(f"削除ページ {i + 1}")

        # 削除後に出品フラグをすべてfalseに設定
        upload_data_list = utils.load_json(utils.upload_data) or []
        for item in upload_data_list:
            item["exhibited"] = False
        utils.save_json(upload_data_list, utils.upload_data)


if __name__ == "__main__":
    bot = Bot()

    #bot.update_deadline("2026/06/14")
    # bot.set_unexhibited(4100)

    #bot.update_none_stock()

    #bot.increase_price()
    #bot.discount_price(utils.discount_percent)
    #bot.update_size()

    bot.delete()
