"""簡易デモの通しテスト（会員の入館〜管理画面の取消・集計まで）。
使い方: python3 e2e_test.py [URL]   既定はローカルの index.html
"""
import sys
from pathlib import Path
from playwright.sync_api import sync_playwright

URL = sys.argv[1] if len(sys.argv) > 1 else (Path(__file__).parent / "index.html").resolve().as_uri()
SHOTS = Path(__file__).parent / "shots"
SHOTS.mkdir(exist_ok=True)
errors = []
results = []


def check(name, cond):
    results.append((name, bool(cond)))
    print(("OK  " if cond else "NG  ") + name)


with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page(viewport={"width": 390, "height": 844})
    pg.on("pageerror", lambda e: errors.append(str(e)))
    pg.goto(URL)
    pg.wait_for_selector("text=簡易デモ：画面一覧")

    # 平日 13:00 に固定（追加料金なし）
    pg.fill("#fakeNow", "2026-10-14T13:00")
    pg.click("#fakeApply")

    # ログイン失敗 → 成功
    pg.goto(URL + "#/login")
    pg.fill("#no", "M999")
    pg.click("#login")
    check("誤った会員番号はエラー表示", pg.is_visible("text=メールアドレスか会員番号が違います"))
    pg.fill("#no", "M001")
    pg.click("#login")
    pg.wait_for_selector("#mcard")
    check("会員証に氏名と会社名", pg.is_visible("text=甲野 花子") and pg.is_visible("text=株式会社みなと物産"))
    check("月初付与 3,000pt", pg.inner_text("#pts") == "3,000")
    t1 = pg.inner_text("#clock")
    pg.wait_for_timeout(1300)
    t2 = pg.inner_text("#clock")
    check(f"時刻が秒まで動く ({t1}→{t2})", t1 != t2 and len(t1) == 8)
    pg.screenshot(path=str(SHOTS / "01_card.png"))

    # QR（デモボタン）→ コース選択（平日＝追加料金なし）
    pg.click("#toScan")
    pg.click("text=みなとの湯 本店 のQRを読み込んだことにする")
    pg.wait_for_selector("text=① コースを選んでください", timeout=5000)
    pg.click("text=入浴＋岩盤浴")
    check("平日は追加料金なし", pg.is_visible("text=本日の追加料金はありません"))
    check("平日の店頭払い 0円", pg.inner_text("#cash") == "0円")
    pg.click("#enter")
    pg.wait_for_selector("text=入館受付が完了しました")
    pg.screenshot(path=str(SHOTS / "02_done.png"))
    pg.goto(URL + "#/card")
    check("1,600pt 差し引き後 1,400pt", pg.inner_text("#pts") == "1,400")
    check("同日2回目は不可の表示", pg.is_visible("text=ご利用は1日1回まで"))

    # 土曜の深夜 23:30 → 土日＋深夜、ポイント不足
    pg.fill("#fakeNow", "2026-10-17T23:30")
    pg.click("#fakeApply")
    pg.goto(URL + "#/scan")
    pg.click("text=サウナ蒸 駅前店 のQRを読み込んだことにする")
    pg.wait_for_selector("text=① コースを選んでください", timeout=5000)
    pg.click("text=サウナ フリータイム")
    sur = pg.inner_text("#surAlert")
    check("土日料金と深夜料金を両方表示", "土日料金" in sur and "深夜料金" in sur)
    check("ポイント不足の表示", pg.is_visible("#shortAlert"))
    # 2,200pt − 残1,400pt = 不足800円 + 土日500 + 深夜500 = 1,800円
    check("店頭払い 1,800円", pg.inner_text("#cash") == "1,800円")
    pg.screenshot(path=str(SHOTS / "03_surcharge.png"), full_page=True)
    pg.click("#enter")
    pg.wait_for_selector("text=入館受付が完了しました")
    pg.goto(URL + "#/card")
    check("不足時は残0pt", pg.inner_text("#pts") == "0")

    # 祝日 10/12(月)
    pg.fill("#fakeNow", "2026-10-12T10:00")
    pg.click("#fakeApply")
    pg.goto(URL + "#/scan")
    pg.click("text=みなとの湯 本店 のQRを読み込んだことにする")
    pg.wait_for_selector("text=① コースを選んでください", timeout=5000)
    pg.click("text=入浴のみ")
    check("祝日料金を表示", "祝日料金" in pg.inner_text("#surAlert"))
    pg.goto(URL + "#/card")

    # 管理画面（PC幅）
    pg.set_viewport_size({"width": 1280, "height": 900})
    pg.fill("#fakeNow", "2026-10-20T10:00")
    pg.click("#fakeApply")
    pg.goto(URL + "#/admin/monthly")
    fac = pg.inner_text("#facTable")
    # みなとの湯: 1,600pt×80%=1,280円 / サウナ蒸: 1,400pt×75%=1,050円
    check("精算額 みなとの湯 1,280円", "1,280円" in fac)
    check("精算額 サウナ蒸 1,050円", "1,050円" in fac)
    check("企業別 利用人数1人・2回", "1人" in pg.inner_text("#coTable") and "2回" in pg.inner_text("#coTable"))
    pg.screenshot(path=str(SHOTS / "04_monthly.png"), full_page=True)

    # 取消でポイントが戻る
    pg.goto(URL + "#/admin/visits")
    pg.once("dialog", lambda d: d.accept())
    pg.click("[data-cv=V0001]")
    check("取消済の表示", pg.is_visible("text=取消済"))
    pg.goto(URL + "#/admin/members")
    check("取消で1,600pt戻る", "1,600" in pg.inner_text("#memTable"))

    # CSV一括登録
    pg.click("#imp")
    check("CSV 2件登録", pg.is_visible("text=2件を登録しました"))
    check("CSV登録者に付与済み", "丁野 美咲" in pg.inner_text("#memTable"))

    # 料金をプログラム変更なしで変更 → 会員画面に反映
    pg.goto(URL + "#/admin/facilities")
    inp = pg.locator("input[data-k=K1][data-f=points]")
    inp.fill("1000")
    inp.dispatch_event("change")
    pg.goto(URL + "#/login")
    pg.fill("#em", "misaki@example.com")
    pg.fill("#no", "M004")
    pg.click("#login")
    pg.wait_for_selector("#mcard")
    pg.goto(URL + "#/scan")
    pg.click("text=みなとの湯 本店 のQRを読み込んだことにする")
    pg.wait_for_selector("text=① コースを選んでください", timeout=5000)
    check("料金変更が会員画面に反映(1,000pt)", pg.is_visible("text=1,000pt"))

    # QR発行・作り直しで古いQRが無効
    pg.goto(URL + "#/admin/qr")
    pg.wait_for_selector("#q_F1 img, #q_F1 canvas")
    check("QR画像が出る", pg.locator("#q_F1 img, #q_F1 canvas").count() > 0)
    old = pg.evaluate("JSON.parse(localStorage.getItem('onsen_welfare_demo_v1')).facilities[0].token")
    pg.once("dialog", lambda d: d.accept())
    pg.click("[data-re=F1]")
    pg.goto(URL + f"#/checkin/F1/{old}")
    check("作り直し後の古いQRは無効", pg.is_visible("text=このQRコードは無効です"))
    pg.screenshot(path=str(SHOTS / "05_qr_admin.png"))

    # 企業・施設の管理画面
    pg.goto(URL + "#/company/C1")
    check("企業画面は自社の会員だけ", pg.is_visible("text=甲野 花子") and not pg.is_visible("text=丙野 健太"))
    pg.goto(URL + "#/facility/F2")
    check("施設画面に精算額", pg.is_visible("#facPay"))

    # 来月にすると自動付与（繰り越しなし）
    pg.fill("#fakeNow", "2026-11-01T09:00")
    pg.click("#fakeApply")
    pg.goto(URL + "#/admin/members")
    check("翌月1日に3,000ptへ付与し直し", "3,000" in pg.inner_text("#memTable"))
    b.close()

# ダークモードのPCでも明るい配色のまま
with sync_playwright() as p2:
    b2 = p2.chromium.launch()
    pg2 = b2.new_page(color_scheme="dark")
    pg2.goto(URL)
    pg2.wait_for_selector("text=簡易デモ：画面一覧")
    bg = pg2.evaluate("getComputedStyle(document.body).backgroundColor")
    check(f"ダークモードでも背景が明るい ({bg})", bg == "rgb(246, 248, 250)")
    pg2.screenshot(path=str(SHOTS / "06_dark_os.png"))
    b2.close()

check(f"JSエラー 0件 {errors}", not errors)
ng = [n for n, ok in results if not ok]
print(f"\n{len(results) - len(ng)}/{len(results)} OK")
sys.exit(1 if ng else 0)
