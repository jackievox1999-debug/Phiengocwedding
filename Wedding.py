# -*- coding: utf-8 -*-
from flask import Flask, flash, jsonify, redirect, render_template, request, url_for
from google.oauth2 import service_account
from googleapiclient.discovery import build
from datetime import datetime
import os
import json

# ======================== CONFIG GOOGLE SHEETS ========================
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

GOOGLE_CREDENTIALS_FILE = "web-tool-jackievo-f106962d73f6.json"
SPREADSHEET_ID = "1boziWkpb9bpb8G6u4yEU1YNDVWfpkaXD6aQ5y_bf9rc"

SHEET_CHURCH = "NhaTho"
SHEET_RESTAURANT = "NhaHang"

# ============================= FLASK APP ==============================
app = Flask(__name__)
app.secret_key = "wedding-secret-key-123"

# ===================== NGROK SKIP WARNING (bỏ trang cảnh báo) =====================
@app.after_request
def add_ngrok_skip_header(response):
    # Chỉ cần header này là ngrok free sẽ bỏ trang warning
    response.headers["ngrok-skip-browser-warning"] = "true"
    return response


# ========================= GUESTBOOK (SỔ LƯU BÚT) =========================
# Lưu lời chúc dạng JSON Lines (.txt): mỗi dòng là 1 JSON object.
# File nằm cạnh Wedding.py để dễ deploy (cùng folder).
GUESTBOOK_TXT = os.path.join(os.path.dirname(__file__), "guestbook.txt")

def _guestbook_read_all():
    items = []
    if os.path.exists(GUESTBOOK_TXT):
        with open(GUESTBOOK_TXT, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    items.append(json.loads(line))
                except Exception:
                    # Bỏ qua dòng lỗi để không làm hỏng toàn bộ danh sách
                    continue
    return items

def _guestbook_append(item: dict):
    # Ghi 1 dòng JSON (ensure_ascii=False để giữ tiếng Việt)
    os.makedirs(os.path.dirname(GUESTBOOK_TXT) or ".", exist_ok=True)
    with open(GUESTBOOK_TXT, "a", encoding="utf-8") as f:
        f.write(json.dumps(item, ensure_ascii=False) + "\n")


# --------- HÀM XỬ LÝ SỐ ĐIỆN THOẠI ---------

def normalize_phone(phone: str) -> str:
    """
    Chuẩn hoá SĐT để so sánh:
    - Lấy toàn bộ chữ số
    - Bỏ 0 đầu → giúp match dù Sheet làm mất 0
    """
    digits = "".join(ch for ch in phone if ch.isdigit())
    return digits.lstrip("0")


def mask_phone(phone: str) -> str:
    """Ẩn bớt SĐT khi hiển thị: 086*****763."""
    digits = "".join(ch for ch in phone if ch.isdigit())
    if len(digits) <= 6:
        return digits
    return digits[:3] + "*" * (len(digits) - 6) + digits[-3:]


def build_row(data):
    """Tạo dòng ghi vào Google Sheet — luôn giữ số 0 đầu bằng cách thêm ' trước."""
    phone_raw = data.get("phone", "").strip()
    phone_cell = f"'{phone_raw}" if phone_raw else ""

    return [
        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        data.get("name", ""),
        phone_cell,
        data.get("guest_count", ""),
        data.get("attend", ""),
        data.get("note", ""),
    ]


def get_sheets_service():
    creds = service_account.Credentials.from_service_account_file(
        GOOGLE_CREDENTIALS_FILE, scopes=SCOPES
    )
    return build("sheets", "v4", credentials=creds).spreadsheets()


# ======================= HÀM LÀM VIỆC VỚI SHEET =======================

def upsert_rsvp(sheet_name, data):
    """Ghi dữ liệu vào sheet theo kiểu upsert."""
    sheets = get_sheets_service()

    phone_input = data.get("phone", "").strip()
    if not phone_input:
        raise ValueError("Phone number is required")

    phone_norm_input = normalize_phone(phone_input)

    result = sheets.values().get(
        spreadsheetId=SPREADSHEET_ID,
        range=f"{sheet_name}!A2:F",
    ).execute()

    rows = result.get("values", [])
    target_row_index = None

    for idx, row in enumerate(rows, start=2):
        stored_phone = row[2].strip() if len(row) >= 3 else ""
        if normalize_phone(stored_phone) == phone_norm_input:
            target_row_index = idx
            break

    row_values = build_row(data)

    if target_row_index is not None:
        update_range = f"{sheet_name}!A{target_row_index}:F{target_row_index}"
        sheets.values().update(
            spreadsheetId=SPREADSHEET_ID,
            range=update_range,
            valueInputOption="USER_ENTERED",
            body={"values": [row_values]},
        ).execute()
    else:
        sheets.values().append(
            spreadsheetId=SPREADSHEET_ID,
            range=f"{sheet_name}!A:Z",
            valueInputOption="USER_ENTERED",
            body={"values": [row_values]},
        ).execute()


def get_all_rsvp(sheet_name):
    """Lấy danh sách khách mời."""
    sheets = get_sheets_service()
    result = sheets.values().get(
        spreadsheetId=SPREADSHEET_ID,
        range=f"{sheet_name}!A2:F",
    ).execute()

    rows = result.get("values", [])
    data = []

    for row in rows:
        ts = row[0] if len(row) > 0 else ""
        name = row[1] if len(row) > 1 else ""
        phone_cell = row[2] if len(row) > 2 else ""
        attend = row[4] if len(row) > 4 else ""
        data.append({
            "time": ts,
            "name": name,
            "phone_raw": phone_cell,
            "phone_mask": mask_phone(phone_cell),
            "attend": attend,
        })

    return data


def update_attendance(sheet_name, phone_input, new_attend, new_note):
    """Sửa trạng thái khách theo số điện thoại."""
    sheets = get_sheets_service()

    phone_input = phone_input.strip()
    if not phone_input:
        return False

    phone_norm_input = normalize_phone(phone_input)

    result = sheets.values().get(
        spreadsheetId=SPREADSHEET_ID,
        range=f"{sheet_name}!A2:F",
    ).execute()

    rows = result.get("values", [])
    target_row_index = None
    old_row = None

    for idx, row in enumerate(rows, start=2):
        stored_phone = row[2].strip() if len(row) >= 3 else ""
        if normalize_phone(stored_phone) == phone_norm_input:
            target_row_index = idx
            old_row = row
            break

    if not old_row:
        return False

    old_name = old_row[1]
    old_guest_count = old_row[3]
    old_old_attend = old_row[4]
    old_note = old_row[5]

    phone_cell = f"'{phone_input}"  # giữ số 0 đầu

    updated_row = [
        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        old_name,
        phone_cell,
        old_guest_count,
        new_attend or old_old_attend,
        new_note if new_note else old_note,
    ]

    update_range = f"{sheet_name}!A{target_row_index}:F{target_row_index}"

    sheets.values().update(
        spreadsheetId=SPREADSHEET_ID,
        range=update_range,
        valueInputOption="USER_ENTERED",
        body={"values": [updated_row]},
    ).execute()

    return True


# =============================== ROUTES ================================

@app.route("/")
def index():
    return render_template("wedding1.html")


@app.route("/rsvp/church", methods=["GET", "POST"])
def rsvp_church():
    if request.method == "POST":
        form = {
            "name": request.form.get("name"),
            "phone": request.form.get("phone"),
            "guest_count": request.form.get("guest_count"),
            "attend": request.form.get("attend"),
            "note": request.form.get("note"),
        }

        upsert_rsvp(SHEET_CHURCH, form)

        return render_template(
            "confirm.html",
            guest_name=form["name"],
            is_church=True,
            attend_status=form["attend"]   # 🔥 QUAN TRỌNG
        )

    return render_template(
        "rsvp_form.html",
        title="Xác nhận tham gia Nghi lễ Hôn phối (Nhà Thờ)",
        action_url=url_for("rsvp_church"),
        bg_image="church",
    )


@app.route("/rsvp/restaurant", methods=["GET", "POST"])
def rsvp_restaurant():
    if request.method == "POST":
        form = {
            "name": request.form.get("name"),
            "phone": request.form.get("phone"),
            "guest_count": request.form.get("guest_count"),
            "attend": request.form.get("attend"),
            "note": request.form.get("note"),
        }

        upsert_rsvp(SHEET_RESTAURANT, form)

        return render_template(
            "confirm.html",
            guest_name=form["name"],
            is_church=False,
            attend_status=form["attend"]   # 🔥 QUAN TRỌNG
        )

    return render_template(
        "rsvp_form.html",
        title="Xác nhận tham gia Tiệc cưới (Nhà Hàng)",
        action_url=url_for("rsvp_restaurant"),
        bg_image="restaurant",
    )


@app.route("/guest-list", methods=["GET", "POST"])
def guest_list():
    message = None
    message_type = None

    if request.method == "POST":
        phone = request.form.get("phone")
        target = request.form.get("target")
        attend = request.form.get("attend")
        note = request.form.get("note")

        sheet = SHEET_CHURCH if target == "church" else SHEET_RESTAURANT
        ok = update_attendance(sheet, phone, attend, note)

        if ok:
            message = "Đã cập nhật thành công."
            message_type = "success"
        else:
            message = "Không tìm thấy số điện thoại."
            message_type = "error"

    church_list = get_all_rsvp(SHEET_CHURCH)
    restaurant_list = get_all_rsvp(SHEET_RESTAURANT)

    return render_template(
        "guest_list.html",
        church_list=church_list,
        restaurant_list=restaurant_list,
        message=message,
        message_type=message_type,
        limit_date="20/03/2026"
    )


@app.route("/moments")
def moments():
    return render_template("moments.html")



# ========================= GUESTBOOK API ROUTES ==========================
@app.get("/guestbook/list")
def guestbook_list_api():
    """Trả về danh sách lời chúc (mới nhất trước)."""
    items = _guestbook_read_all()
    # mới nhất trước
    items.reverse()
    return jsonify(items)

@app.post("/guestbook/add")
def guestbook_add_api():
    """Nhận lời chúc từ form (name, message, icon) và lưu vào guestbook.txt."""
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    message = (data.get("message") or "").strip()
    icon = (data.get("icon") or "💗").strip()

    if not name or not message:
        return jsonify({"ok": False, "error": "Missing name/message"}), 400

    item = {
        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "name": name[:80],
        "icon": icon[:8],
        "message": message[:1000],
    }
    _guestbook_append(item)
    return jsonify({"ok": True})


# ============================== MAIN ==================================

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001, debug=True)
