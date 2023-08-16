import time

from selenium import webdriver
from selenium.common import UnexpectedAlertPresentException

from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait


def init_driver():
    is_mikistyle = True
    options = webdriver.ChromeOptions()
    # ヘッドレスモード
    # options.add_argument('--headless')
    # 絶対パス指定
    login_data_path = fr"C:\Users\boost\Documents\SourceTreePrivate\selenium-login\{'mikistyle' if is_mikistyle else 'mikistore'}"
    options.add_argument('--user-data-dir=' + login_data_path)
    return webdriver.Chrome(options=options)


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
    page_mode = PageMode.Request

    def __init__(self):
        self.driver = init_driver()
        self.url = f"https://www.buyma.com/my/sell/?status={Bot.page_mode}"

    def driver_wait(self, target, value):
        """
        要素表示までの待機
        """
        WebDriverWait(self.driver, 20).until(EC.presence_of_element_located((target, value)))

    def all_select_temp(self):
        """
        ある１ページの全商品を選択
        """
        # 表示件数を100にする
        self.driver.find_element(By.CLASS_NAME, "js-row-count-options").click()
        self.driver.find_elements(By.CSS_SELECTOR, ".js-row-count-options option")[-1].click()

        # すべての商品の選択
        self.driver.find_element(By.CLASS_NAME, "js-checkbox-check-all").click()
        self.driver.find_element(By.CLASS_NAME, "my_action_output").click()

    def update_deadline(self, deadline):
        """
        購入期限の更新
        :param deadline: 購入期限
        """
        for i in range(50):
            self.driver.get(self.url + (f"&page={i + 1}" if Bot.page_mode == PageMode.Listing else ""))

            self.all_select_temp()

            # 編集
            self.driver.find_element(By.CLASS_NAME, "js-chk-edit-checked").click()
            try:
                # 出品停止の場合用に、出品中に変更
                self.driver.find_element(By.ID, "rdoSyupinStatus1").click()
            except UnexpectedAlertPresentException:
                print("商品無し")
                raise Exception
            # 期限の変更フォーム
            self.driver.find_element(By.ID, "rdoYukodateEditKbn1").click()
            self.driver.find_element(By.CLASS_NAME, "hasDatepicker").send_keys(deadline)
            # 決定
            self.driver.find_element(By.ID, "confirmButton").click()
            # 再確認
            self.driver_wait(By.ID, "completeButton")
            self.driver.find_element(By.ID, "completeButton").click()
            print(f"update page {i + 1}")

    def delete(self):
        for i in range(100):
            self.driver.get(self.url)

            self.all_select_temp()
            # 削除
            self.driver.find_element(By.CLASS_NAME, "js-chk-del-checked").click()
            try:
                # 決定
                self.driver.find_element(By.ID, "delete").click()
            except UnexpectedAlertPresentException:
                print("商品無し")
                raise Exception
            print(f"delete turn {i + 1}")

    def set_discount(self, discount_percent, is_price_up=False):
        """
        パーセントベースの価格変更
        :param discount_percent: 率
        :param is_price_up: 値上げかどうか
        """
        for i in range(50):
            self.driver.get(self.url + f"&page={i + 1}")

            self.all_select_temp()
            try:
                # 編集
                self.driver.find_element(By.CLASS_NAME, "js-chk-edit-checked").click()
            except UnexpectedAlertPresentException:
                print("商品無し")
                raise Exception
            # デフォルトは値下げ
            self.driver.find_element(By.ID, "rdoPriceEditKbn1").click()
            if is_price_up:  # 値上げ
                self.driver.find_element(By.ID, 'lstPriceEditStyle').click()
                self.driver.find_elements(By.CSS_SELECTOR, '#lstPriceEditStyle option')[2].click()
            self.driver.find_element(By.NAME, "txtPriceEdit").send_keys(discount_percent)
            # 決定
            self.driver.find_element(By.ID, "confirmButton").click()
            # 再確認
            self.driver_wait(By.ID, "completeButton")
            self.driver.find_element(By.ID, "completeButton").click()
            print(f"discount page {i + 1}")


if __name__ == '__main__':
    bot = Bot()
    bot.update_deadline("2023/09/9")
    # bot.delete()
    # bot.set_discount(10)
