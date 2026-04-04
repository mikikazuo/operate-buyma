from typing import Dict, List

import utils

# 定数定義
MAX_CATEGORY_DEPTH = 5
DEPTH_PREFIX = "depth"


class CategoryManager:
    """BUYMAカテゴリー管理クラス"""

    def __init__(self):
        self.main_data_path = utils.main_data
        self.category_dict_path = utils.category_dict_path

    def filter_by_gender(self, data: Dict) -> bool:
        """性別でフィルタリング"""
        return data["gender"] == ("woman" if utils.is_women else "men")

    def get_depth_key(self, depth: int) -> str:
        """深さキーを生成"""
        return f"{DEPTH_PREFIX}{depth}"

    def find_empty_categories(self, category_dict: Dict) -> List[List[str]]:
        """カテゴリー辞書から空の配列を持つカテゴリーを収集"""
        empty_paths = []
        for depth_dict in category_dict.values():
            self._find_empty_in_depth(depth_dict, [], empty_paths)
        return empty_paths

    def _find_empty_in_depth(
        self, current_dict: Dict, path: List[str], empty_paths: List[List[str]]
    ):
        """再帰的に空の配列を探す"""
        for key, value in current_dict.items():
            if isinstance(value, list) and len(value) == 0:
                empty_paths.append(path + [key])
            elif isinstance(value, dict):
                self._find_empty_in_depth(value, path + [key], empty_paths)

    def make_category_dict(self) -> List[List[str]]:
        """
        メインデータからカテゴリー辞書を作成・更新
        新規カテゴリーを返す
        """
        print("=== カテゴリー辞書の作成開始 ===")

        main_data = utils.load_json(self.main_data_path) or []
        category_dict = utils.load_json(self.category_dict_path)
        new_categories = []

        for data in main_data:
            category = data["category"]
            depth = len(category)
            depth_key = self.get_depth_key(depth)

            # depth キーが存在しない場合は作成
            category_dict.setdefault(depth_key, {})

            # カテゴリーを辿る
            current = category_dict[depth_key]

            # 最後の要素以外を辿る
            for category_name in category[:-1]:
                if category_name not in current:
                    current[category_name] = {}
                current = current[category_name]

            # 最後の要素を処理
            last_category = category[-1]
            if last_category not in current:
                current[last_category] = []
                print(f"新規カテゴリー発見: {category}")

                new_categories.append(category)

        # 保存
        utils.save_json(category_dict, self.category_dict_path)

        print(f"=== 完了: 新規カテゴリー数 {len(new_categories)} ===")
        return new_categories

    def input_category_mapping(
        self, max_depth: int = MAX_CATEGORY_DEPTH
    ) -> tuple[List[str], bool]:
        """
        ユーザーからカテゴリーマッピングを入力

        Returns:
            (カテゴリーリスト, スルーフラグ)
        """
        category = []
        through = False

        for i in range(max_depth):
            title = (
                input(f"カテゴリー名{i}: ").replace('"', "").replace(",", "").strip()
            )

            if title == "t":
                through = True
                break

            if not title:
                break

            category.append(title)

        return category, through

    def assign_new_category(self) -> None:
        """
        カテゴリー辞書内の空配列にマッピングを割り当てる
        """
        print("=== カテゴリーの割り当て開始 ===")

        context, page = utils.browser_ini("user_data/chrome_user_data")
        main_data = utils.load_json(self.main_data_path) or []
        category_dict = utils.load_json(self.category_dict_path)

        # 空の配列を持つカテゴリーを収集
        empty_categories = self.find_empty_categories(category_dict)

        if not empty_categories:
            print("割り当て対象のカテゴリーはありません")
            context.close()
            return

        for category in empty_categories:
            # サンプルURLを収集
            samples = [
                item["url"] for item in main_data if item.get("category") == category
            ]

            if not samples:
                print(f"Warning: サンプルが見つかりません - {category}")
                continue

            depth = len(category)
            depth_key = self.get_depth_key(depth)

            # カテゴリー辞書の該当箇所まで移動
            current = category_dict[depth_key]
            for name in category[:-1]:
                current = current[name]

            print("=" * 50)
            print(f"カテゴリー: {category}")
            print(f"サンプル数: {len(samples)}")

            for idx, sample_url in enumerate(samples):
                page.goto(utils.product_url + sample_url)
                print("-" * 50)

                is_last_sample = idx == len(samples) - 1

                if is_last_sample:
                    # 最後のサンプルは確実に入力させる
                    while True:
                        print("Note: Last Sample")
                        mapping, through = self.input_category_mapping()
                        if len(mapping) > 0 or through:
                            break
                else:
                    mapping, through = self.input_category_mapping()

                if through:
                    print("スルー")
                    # マッピングを保存（参照型のため、辞書の内容が直接更新される）
                    current[category[-1]] = None
                    utils.save_json(category_dict, self.category_dict_path)
                    break
                elif len(mapping) > 0:
                    # マッピングを保存（参照型のため、辞書の内容が直接更新される）
                    current[category[-1]] = mapping
                    utils.save_json(category_dict, self.category_dict_path)
                    break

        # ブラウザをクリーンアップ
        context.close()

        print("=== カテゴリーの割り当て完了 ===")


def main():
    """メイン処理"""
    manager = CategoryManager()

    # カテゴリー辞書の作成
    manager.make_category_dict()

    # カテゴリーの割り当て
    manager.assign_new_category()


if __name__ == "__main__":
    main()
