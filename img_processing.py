import requests
import cv2
import numpy as np
import math
import time

import utils


# グラデーション
def get_gradation_2d(start, stop, width, height, is_horizontal):
    if is_horizontal:
        return np.tile(np.linspace(start, stop, width), (height, 1))
    else:
        return np.tile(np.linspace(start, stop, height), (width, 1)).T


def get_gradation_3d(width, height, start_list, stop_list, is_horizontal_list):
    result = np.zeros((height, width, len(start_list)), dtype=np.float64)

    for i, (start, stop, is_horizontal) in enumerate(
        zip(start_list, stop_list, is_horizontal_list)
    ):
        result[:, :, i] = get_gradation_2d(start, stop, width, height, is_horizontal)

    return result


# 画像ダウンロード  pyautogui.FailSafeException: PyAutoGUI f
def download_img(url, file_name):
    while True:
        try:
            r = requests.get(url, stream=True)
        except requests.exceptions.ConnectTimeout:
            print("retry access")
            time.sleep(10)
            continue
        except requests.exceptions.ConnectionError:
            print("retry error access")
            time.sleep(10)
            continue
        else:
            if r.status_code == 200:
                with open(file_name, "wb") as f:
                    f.write(r.content)
                    return True
            else:
                print("error status img")
                break

    return False


def download_Allimg(imgList, mynum):
    successCount = 0
    for index, url in enumerate(imgList):
        # 日本語: 絶対URLの場合はそのまま、相対パスの場合はベースURLを付与
        # (Giglioなどでドメインが分散しているケースに対応)
        target_url = url if url.startswith("http") else utils.img_url + url

        if download_img(
            target_url,
            "img/upload" + str(mynum) + "_" + str(successCount + 1) + ".jpg",
        ):
            successCount = successCount + 1
    return successCount


# 画像加工
def imgEdit(nowIndex, successCount, mynum):
    def imgPrint(x, y, deg, scale, img, baseImg):
        baseRow, baseCol, base = baseImg.shape
        row, col, c = img.shape

        mat = np.array([[0, 0, x], [0, 0, y]], dtype=np.float32)
        affine_matrix = np.float32(
            cv2.getRotationMatrix2D(center=(col / 2, row / 2), angle=deg, scale=scale)
        )
        dst = cv2.warpAffine(
            img,
            mat + affine_matrix,
            dsize=(baseCol, baseRow),
            dst=baseImg,
            borderMode=cv2.BORDER_TRANSPARENT,
            flags=cv2.INTER_LANCZOS4,
        )
        return dst

    if nowIndex < successCount - 1:
        isTwo = True
    else:
        isTwo = False

    fg_img = cv2.imread("img/upload" + str(mynum) + "_" + str(nowIndex + 1) + ".jpg")
    row1, col1, c = fg_img.shape
    maxWide = row1 if row1 > col1 else col1

    # 横に配置するか　縦に配置するか
    # rowが縦y　colが横x
    setSide = True
    diffSpace = 0
    if isTwo:
        imgPath = "img/upload" + str(mynum) + "_" + str(nowIndex + 2) + ".jpg"
        img = cv2.imread(imgPath)
        row2, col2, c = img.shape
        ideaWide = row2 if row2 > col2 else col2
        maxWide = maxWide if maxWide > ideaWide else ideaWide

        # 縦の合計の方が大きい　つまり横に配置すべき
        setSide = True if col2 + col1 < row2 + row1 else False
        maxWide = (
            maxWide
            if maxWide > col2 + col1 or maxWide > row2 + row1
            else col2 + col1 if setSide else row2 + row1
        )
        diffSpace = maxWide - (row2 + row1) if setSide else maxWide - (col2 + col1)

    array = get_gradation_3d(
        maxWide, maxWide, (15, 15, 15), (0, 0, 0), (True, True, False)
    )
    imageArray = np.uint8(array)
    # 画像にアフィン変換行列を適用する。
    h, w, c = imageArray.shape
    array2 = get_gradation_3d(
        maxWide, maxWide, (255, 255, 255), (255, 255, 255), (True, True, False)
    )
    imageArray2 = np.uint8(array2)

    imageArraySet = imgPrint(0, 0, 0, 0.98, imageArray2, imageArray)
    baseRow, baseCol, base = imageArraySet.shape

    imgPath = "img/upload" + str(mynum) + "_" + str(nowIndex + 1) + ".jpg"
    img = cv2.imread(imgPath)
    row, col, c = img.shape

    # 画像左上が座標
    if setSide:
        x = 0 if isTwo else baseCol / 2 - col / 2
        y = 0
    else:
        x = 0
        y = 0 if isTwo else baseRow / 2 - row / 2

    dst = imgPrint(x, y, 0, 0.94, img, imageArraySet)

    if isTwo:
        imgPath = "img/upload" + str(mynum) + "_" + str(nowIndex + 2) + ".jpg"
        img = cv2.imread(imgPath)
        row, col, c = img.shape

        if setSide:
            x = baseCol - col
            y = 0
        else:
            x = 0
            y = baseRow - row

        dst = imgPrint(x, y, 0, 0.94, img, dst)

        # ロゴ

        if utils.is_mikistyle:
            rogo = cv2.imread("img/mikistyle.jpg")
        else:
            rogo = cv2.imread("img/mikistore.jpg")
        rowsa, colsa, ca = rogo.shape
        # 2023/7/30　座標がずれたため廃止（再調整が手間）
        # dst = imgPrint(-colsa/2+maxWide/2, -rowsa + maxWide, 0, 0.60* maxWide/680, rogo, dst)

    cv2.imwrite("img/madeimg" + str(int(nowIndex / 2) + 1) + ".jpg", dst)


# 画像加工1枚バージョン
def imgEditOne(nowIndex, successCount, mynum):
    def imgPrint(x, y, deg, scale, img, baseImg):
        baseRow, baseCol, base = baseImg.shape
        row, col, c = img.shape

        mat = np.array([[0, 0, x], [0, 0, y]], dtype=np.float32)
        affine_matrix = np.float32(
            cv2.getRotationMatrix2D(center=(col / 2, row / 2), angle=deg, scale=scale)
        )
        dst = cv2.warpAffine(
            img,
            mat + affine_matrix,
            dsize=(baseCol, baseRow),
            dst=baseImg,
            borderMode=cv2.BORDER_TRANSPARENT,
            flags=cv2.INTER_LANCZOS4,
        )
        return dst

    # 前景画像、背景画像を読み込む。
    fg_img = cv2.imread("img/upload" + str(mynum) + "_" + str(nowIndex + 1) + ".jpg")
    # 画像自体にサイズがない場合があるため判定追加
    if not hasattr(fg_img, "shape"):
        return False
    rows, cols, c = fg_img.shape
    height = rows
    width = cols
    maxWide = height if height > width else width
    # array = get_gradation_3d(width, height, (225, 245, 255), (220, 210, 252), (True, False, False))
    # どっちも15じゃないとなぜか上のの関数を使うと白くなる
    array = get_gradation_3d(
        maxWide, maxWide, (15, 15, 15), (15, 15, 15), (True, True, False)
    )
    imageArray = np.uint8(array)
    imageArray3 = np.uint8(array)

    array2 = get_gradation_3d(
        maxWide, maxWide, (255, 255, 255), (255, 255, 255), (True, True, False)
    )
    imageArray2 = np.uint8(array2)

    imageArraySet = imgPrint(0, 0, 0.0, 0.99, imageArray2, imageArray)

    imgPath = "img/upload" + str(mynum) + "_" + str(nowIndex + 1) + ".jpg"
    img = cv2.imread(imgPath)
    row, col, c = img.shape
    baseRow, baseCol, base = imageArraySet.shape
    if row > col:
        x = baseCol / 2 - col / 2
        y = 0
    else:
        x = 0
        y = baseRow / 2 - row / 2
    dst = imgPrint(x, y, 0, 0.94, img, imageArraySet)

    # 2023/9/18　ロゴを非表示にした
    # if utils.is_mikistyle:
    #     rogo = cv2.imread('img/mikistyle.jpg')
    # else:
    #     rogo = cv2.imread('img/mikistore.jpg')
    # rows, cols, c = rogo.shape
    # angle = 0
    # scale = 0.7 * maxWide/1044
    # #x = -cols / 2 + maxWide / 2
    # x = -cols * scale *1.9 + maxWide
    # y = -rows*scale*2 + maxWide
    #
    # imgpasteAll = imgPrint(x, y, angle, scale, rogo, dst)
    cv2.imwrite("img/madeimg" + str(int(nowIndex) + 1) + ".jpg", dst)  # imgpasteAll)
    return True
