
import os, io, json
from datetime import date, datetime
from pathlib import Path

import pandas as pd
import streamlit as st
import plotly.express as px
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, HRFlowable
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_RIGHT, TA_LEFT

# ─────────────────────────────────────────────────────────────────────────────
# CONSTANTS
# ─────────────────────────────────────────────────────────────────────────────
NGO_NAME    = "Vihaan Waste Management Services"
NGO_ADDRESS = "Bengaluru, Karnataka, India"
NGO_EMAIL   = "vihaan@example.com"
NGO_PHONE   = "+91 00000 00000"
NGO_GSTIN   = "29XXXXX0000X1ZX"

DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)

SALES_FILE      = DATA_DIR / "sales.csv"
INVENTORY_FILE  = DATA_DIR / "inventory.csv"
PRODUCTION_FILE = DATA_DIR / "production.csv"
WORKERS_FILE    = DATA_DIR / "workers.csv"
TASKS_FILE      = DATA_DIR / "tasks.csv"       # task rates per product per activity
WORK_LOG_FILE   = DATA_DIR / "work_log.csv"    # daily work log entries

ORDER_STATUSES = ["Processing", "Dispatched", "Delivered", "Cancelled"]
PAY_STATUSES   = ["Pending", "Received", "Partial"]
ACTIVITIES     = ["Cutting", "Stitching", "Finishing", "Printing", "Packing", "Quality Check"]

SALES_COLS = [
    "Sale ID","Date","Product Code","Product Name","Product Price",
    "Customer Name","Customer Email","Customer Phone",
    "Order Quantity","Discount %","GST %","Admin & General %",
    "GST Reclaimed","Payment Status","Payment Date",
    "Order Status","Delivery Date","Sale Price","Final Sale Price",
]
INVENTORY_COLS = [
    "Entry ID","Date","Cost Type","Material Name","Quantity Purchased",
    "Cost per Unit","Discount %","GST %","GST Reclaimed",
    "Total Cost","Raw Material Used","Inventory Remaining",
]
PRODUCTION_COLS = [
    "Entry ID","Date","Product Code","Product Name",
    "Units Made","Time Taken (days)","Units Sold","Inventory of Products",
]
WORKERS_COLS  = ["Worker ID","Worker Name","Activity","Active"]
TASKS_COLS    = ["Task ID","Product Code","Product Name","Activity","Rate per Unit"]
WORK_LOG_COLS = ["Log ID","Date","Worker ID","Worker Name","Activity",
                 "Product Code","Product Name","Units Done","Rate per Unit","Earnings"]

# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────
def load(path, cols):
    if Path(path).exists():
        df = pd.read_csv(path, dtype=str)
        for c in cols:
            if c not in df.columns:
                df[c] = ""
        return df[cols]
    return pd.DataFrame(columns=cols)

def save(df, path):
    df.to_csv(path, index=False)

def next_id(df, col):
    if df.empty or df[col].dropna().empty:
        return 1
    nums = pd.to_numeric(df[col], errors="coerce").dropna()
    return int(nums.max()) + 1 if not nums.empty else 1

def compute_sale(price, qty, discount_pct, gst_pct, admin_pct):
    sale_price = price * qty * (1 - discount_pct / 100)
    final      = sale_price * (1 + gst_pct / 100) * (1 + admin_pct / 100)
    return round(price * qty, 2), round(sale_price, 2), round(final, 2)

def compute_material_cost(qty, cpu, disc, gst):
    base = qty * cpu * (1 - disc / 100)
    return round(base * (1 + gst / 100), 2)

def num(df, col):
    return pd.to_numeric(df[col], errors="coerce").fillna(0)

def fmt_inr(v):
    try:
        return f"₹{float(v):,.2f}"
    except Exception:
        return str(v)

# ─────────────────────────────────────────────────────────────────────────────
# PDF INVOICE
# ─────────────────────────────────────────────────────────────────────────────
def generate_invoice_pdf(row: dict) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4,
                            leftMargin=15*mm, rightMargin=15*mm,
                            topMargin=15*mm, bottomMargin=15*mm)
    styles = getSampleStyleSheet()
    brand   = ParagraphStyle("brand",   fontSize=16, leading=20, alignment=TA_CENTER, fontName="Helvetica-Bold")
    sub     = ParagraphStyle("sub",     fontSize=9,  leading=12, alignment=TA_CENTER, textColor=colors.grey)
    heading = ParagraphStyle("heading", fontSize=13, leading=16, fontName="Helvetica-Bold", spaceAfter=4)
    normal  = styles["Normal"]
    right   = ParagraphStyle("right",  fontSize=9,  alignment=TA_RIGHT)
    bold9   = ParagraphStyle("bold9",  fontSize=9,  fontName="Helvetica-Bold")
    reg9    = ParagraphStyle("reg9",   fontSize=9)

    elems = []

    # Header
    elems.append(Paragraph(NGO_NAME, brand))
    elems.append(Paragraph(f"{NGO_ADDRESS}  |  {NGO_EMAIL}  |  {NGO_PHONE}", sub))
    elems.append(Paragraph(f"GSTIN: {NGO_GSTIN}", sub))
    elems.append(Spacer(1, 4*mm))
    elems.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor("#2c6e49")))
    elems.append(Spacer(1, 2*mm))
    elems.append(Paragraph("TAX INVOICE", heading))
    elems.append(Spacer(1, 2*mm))

    # Meta table
    inv_no   = f"INV-{row.get('Sale ID','')}"
    inv_date = row.get("Date", str(date.today()))
    pay_due  = row.get("Delivery Date", "")
    meta_data = [
        [Paragraph("<b>Invoice No:</b>", reg9), Paragraph(inv_no, reg9),
         Paragraph("<b>Invoice Date:</b>", reg9), Paragraph(str(inv_date), reg9)],
        [Paragraph("<b>Order Status:</b>", reg9), Paragraph(row.get("Order Status",""), reg9),
         Paragraph("<b>Delivery Date:</b>", reg9), Paragraph(str(pay_due), reg9)],
        [Paragraph("<b>Payment Status:</b>", reg9), Paragraph(row.get("Payment Status",""), reg9),
         Paragraph("<b>Payment Date:</b>", reg9), Paragraph(str(row.get("Payment Date","")), reg9)],
    ]
    meta_tbl = Table(meta_data, colWidths=[35*mm, 55*mm, 35*mm, 55*mm])
    meta_tbl.setStyle(TableStyle([
        ("GRID",      (0,0),(-1,-1), 0.3, colors.lightgrey),
        ("BACKGROUND",(0,0),(0,-1),  colors.HexColor("#f0f4f0")),
        ("BACKGROUND",(2,0),(2,-1),  colors.HexColor("#f0f4f0")),
        ("VALIGN",    (0,0),(-1,-1), "MIDDLE"),
        ("TOPPADDING",(0,0),(-1,-1), 3),
        ("BOTTOMPADDING",(0,0),(-1,-1), 3),
    ]))
    elems.append(meta_tbl)
    elems.append(Spacer(1, 4*mm))

    # Bill-to
    elems.append(Paragraph("<b>Bill To:</b>", reg9))
    cust_info = [
        row.get("Customer Name","—"),
        row.get("Customer Email",""),
        row.get("Customer Phone",""),
    ]
    for line in cust_info:
        if line:
            elems.append(Paragraph(line, reg9))
    elems.append(Spacer(1, 4*mm))

    # Line items
    price    = float(row.get("Product Price", 0) or 0)
    qty      = float(row.get("Order Quantity", 1) or 1)
    disc     = float(row.get("Discount %", 0) or 0)
    gst      = float(row.get("GST %", 0) or 0)
    admin    = float(row.get("Admin & General %", 0) or 0)
    subtotal = price * qty
    disc_amt = subtotal * disc / 100
    after_disc = subtotal - disc_amt
    gst_amt  = after_disc * gst / 100
    admin_amt= after_disc * admin / 100
    total    = after_disc + gst_amt + admin_amt

    col_headers = ["#","Product","Code","Unit Price","Qty","Discount","Amount"]
    col_widths  = [8*mm, 55*mm, 25*mm, 22*mm, 12*mm, 20*mm, 28*mm]
    items_data  = [col_headers, [
        "1",
        row.get("Product Name",""),
        row.get("Product Code",""),
        fmt_inr(price),
        str(int(qty)),
        f"{disc:.1f}%",
        fmt_inr(subtotal - disc_amt),
    ]]
    items_tbl = Table(items_data, colWidths=col_widths)
    items_tbl.setStyle(TableStyle([
        ("BACKGROUND",   (0,0),(-1,0),  colors.HexColor("#2c6e49")),
        ("TEXTCOLOR",    (0,0),(-1,0),  colors.white),
        ("FONTNAME",     (0,0),(-1,0),  "Helvetica-Bold"),
        ("FONTSIZE",     (0,0),(-1,-1), 8),
        ("ROWBACKGROUNDS",(0,1),(-1,-1),[colors.white, colors.HexColor("#f7f7f7")]),
        ("GRID",         (0,0),(-1,-1), 0.3, colors.lightgrey),
        ("ALIGN",        (3,0),(-1,-1), "RIGHT"),
        ("TOPPADDING",   (0,0),(-1,-1), 4),
        ("BOTTOMPADDING",(0,0),(-1,-1), 4),
    ]))
    elems.append(items_tbl)
    elems.append(Spacer(1, 3*mm))

    # Totals block (right-aligned)
    totals_data = [
        ["Subtotal (before discount)",  fmt_inr(subtotal)],
        [f"Discount ({disc:.1f}%)",     f"- {fmt_inr(disc_amt)}"],
        ["After Discount",              fmt_inr(after_disc)],
        [f"GST ({gst:.1f}%)",           fmt_inr(gst_amt)],
        [f"Admin & General ({admin:.1f}%)", fmt_inr(admin_amt)],
        ["TOTAL",                       fmt_inr(total)],
    ]
    tot_tbl = Table(totals_data, colWidths=[80*mm, 40*mm],
                    hAlign="RIGHT")
    tot_tbl.setStyle(TableStyle([
        ("FONTSIZE",    (0,0),(-1,-1), 9),
        ("ALIGN",       (1,0),(1,-1),  "RIGHT"),
        ("LINEABOVE",   (0,-1),(-1,-1),1, colors.HexColor("#2c6e49")),
        ("FONTNAME",    (0,-1),(-1,-1),"Helvetica-Bold"),
        ("TEXTCOLOR",   (0,-1),(-1,-1),colors.HexColor("#2c6e49")),
        ("TOPPADDING",  (0,0),(-1,-1), 3),
        ("BOTTOMPADDING",(0,0),(-1,-1),3),
        ("GRID",        (0,0),(-1,-2), 0.2, colors.lightgrey),
    ]))
    elems.append(tot_tbl)
    elems.append(Spacer(1, 6*mm))
    elems.append(HRFlowable(width="100%", thickness=0.5, color=colors.lightgrey))
    elems.append(Spacer(1, 2*mm))
    elems.append(Paragraph("Thank you for supporting Vihaan Waste Management Services.", sub))
    elems.append(Paragraph("This is a computer-generated invoice and does not require a physical signature.", sub))

    doc.build(elems)
    buf.seek(0)
    return buf.read()

# ─────────────────────────────────────────────────────────────────────────────
# STREAMLIT APP
# ─────────────────────────────────────────────────────────────────────────────
st.set_page_config(page_title="Vihaan Bag Tracker", page_icon="👜", layout="wide")

st.sidebar.title("👜 Vihaan Bag Tracker")
st.sidebar.caption(NGO_NAME)

SECTIONS = {
    "📋 Inputs": [
        "Sale Details",
        "Inventory Details",
        "Productivity / Workers",
        "Worker & Task Setup",
    ],
    "📊 Analysis": [
        "Top Customers",
        "Top Products Sold",
        "Monthly Cashflow",
        "Fixed vs Flexible Expenses",
        "Worker Productivity & Profit Share",
        "Inventory Status",
    ],
    "🧾 Invoices": ["Generate Invoice"],
}

section = st.sidebar.radio("Section", list(SECTIONS.keys()))
page    = st.sidebar.radio("Page", SECTIONS[section])

# ════════════════════════════════════════════════════════════════════════════
# PAGE: SALE DETAILS
# ════════════════════════════════════════════════════════════════════════════
if page == "Sale Details":
    st.header("Sale Details")
    sales = load(SALES_FILE, SALES_COLS)

    tab_add, tab_view, tab_export = st.tabs(["➕ Add Sale", "📝 View / Edit / Delete", "📤 Export"])

    # ── ADD ──────────────────────────────────────────────────────────────────
    with tab_add:
        with st.form("sale_form", clear_on_submit=True):
            c1, c2, c3 = st.columns(3)
            with c1:
                d     = st.date_input("Date", value=date.today())
                code  = st.text_input("Product Code")
                name  = st.text_input("Product Name")
                price = st.number_input("Product Price (₹)", min_value=0.0, step=10.0)
                qty   = st.number_input("Order Quantity", min_value=0, step=1)
            with c2:
                cust    = st.text_input("Customer Name")
                email   = st.text_input("Customer Email")
                phone   = st.text_input("Customer Phone")
                disc    = st.number_input("Discount %", 0.0, 100.0, 0.0, step=0.5)
                gst     = st.number_input("GST %", 0.0, 100.0, 6.0, step=0.5)
                admin   = st.number_input("Admin & General %", 0.0, 100.0, 10.0, step=0.5)
            with c3:
                gst_r   = st.selectbox("GST Reclaimed?", ["Y", "N"])
                pay_st  = st.selectbox("Payment Status", PAY_STATUSES)
                pay_d   = st.date_input("Payment Date", value=date.today())
                ord_st  = st.selectbox("Order Status", ORDER_STATUSES)
                del_d   = st.date_input("Delivery Date", value=date.today())

            submitted = st.form_submit_button("Add Sale", type="primary")

        if submitted:
            raw_sp, sale_p, final_p = compute_sale(price, qty, disc, gst, admin)
            row = {
                "Sale ID": next_id(sales, "Sale ID"),
                "Date": str(d), "Product Code": code, "Product Name": name,
                "Product Price": price, "Customer Name": cust,
                "Customer Email": email, "Customer Phone": phone,
                "Order Quantity": int(qty), "Discount %": disc,
                "GST %": gst, "Admin & General %": admin,
                "GST Reclaimed": gst_r, "Payment Status": pay_st,
                "Payment Date": str(pay_d) if pay_st != "Pending" else "Pending",
                "Order Status": ord_st, "Delivery Date": str(del_d),
                "Sale Price": raw_sp, "Final Sale Price": final_p,
            }
            sales = pd.concat([sales, pd.DataFrame([row])], ignore_index=True)
            save(sales, SALES_FILE)
            st.success(f"✅ Sale #{row['Sale ID']} added — Sale Price: ₹{raw_sp:,.2f} | Final: ₹{final_p:,.2f}")
            st.rerun()

    # ── VIEW / EDIT / DELETE ─────────────────────────────────────────────────
    with tab_view:
        sales = load(SALES_FILE, SALES_COLS)
        if sales.empty:
            st.info("No sales recorded yet.")
        else:
            # Quick filters
            fc1, fc2, fc3 = st.columns(3)
            with fc1:
                flt_status = st.multiselect("Filter by Order Status", ORDER_STATUSES + ["All"], default=["All"])
            with fc2:
                flt_pay = st.multiselect("Filter by Payment Status", PAY_STATUSES + ["All"], default=["All"])
            with fc3:
                flt_cust = st.text_input("Filter by Customer Name")

            view = sales.copy()
            if "All" not in flt_status and flt_status:
                view = view[view["Order Status"].isin(flt_status)]
            if "All" not in flt_pay and flt_pay:
                view = view[view["Payment Status"].isin(flt_pay)]
            if flt_cust:
                view = view[view["Customer Name"].str.contains(flt_cust, case=False, na=False)]

            st.dataframe(view, use_container_width=True, height=300)

            st.subheader("Edit or Delete a Sale")
            sale_ids = sales["Sale ID"].tolist()
            sel_id   = st.selectbox("Select Sale ID", sale_ids)
            sel_row  = sales[sales["Sale ID"] == str(sel_id)].iloc[0]

            with st.form("edit_sale_form"):
                ec1, ec2, ec3 = st.columns(3)
                with ec1:
                    e_d    = st.date_input("Date", value=pd.to_datetime(sel_row["Date"], errors="coerce") or date.today())
                    e_code = st.text_input("Product Code", value=sel_row["Product Code"])
                    e_name = st.text_input("Product Name", value=sel_row["Product Name"])
                    e_price= st.number_input("Product Price", value=float(sel_row["Product Price"] or 0))
                    e_qty  = st.number_input("Order Quantity", value=int(float(sel_row["Order Quantity"] or 0)), step=1)
                with ec2:
                    e_cust  = st.text_input("Customer Name", value=sel_row["Customer Name"])
                    e_email = st.text_input("Customer Email", value=sel_row["Customer Email"])
                    e_phone = st.text_input("Customer Phone", value=sel_row["Customer Phone"])
                    e_disc  = st.number_input("Discount %", value=float(sel_row["Discount %"] or 0))
                    e_gst   = st.number_input("GST %", value=float(sel_row["GST %"] or 0))
                    e_admin = st.number_input("Admin & General %", value=float(sel_row["Admin & General %"] or 0))
                with ec3:
                    e_gstr  = st.selectbox("GST Reclaimed?", ["Y","N"], index=0 if sel_row["GST Reclaimed"]=="Y" else 1)
                    e_pays  = st.selectbox("Payment Status", PAY_STATUSES,
                                           index=PAY_STATUSES.index(sel_row["Payment Status"]) if sel_row["Payment Status"] in PAY_STATUSES else 0)
                    e_payd  = st.date_input("Payment Date",  value=pd.to_datetime(sel_row["Payment Date"], errors="coerce") or date.today())
                    e_ords  = st.selectbox("Order Status", ORDER_STATUSES,
                                           index=ORDER_STATUSES.index(sel_row["Order Status"]) if sel_row["Order Status"] in ORDER_STATUSES else 0)
                    e_deld  = st.date_input("Delivery Date", value=pd.to_datetime(sel_row["Delivery Date"], errors="coerce") or date.today())

                col_save, col_del = st.columns(2)
                do_save   = col_save.form_submit_button("💾 Save Changes", type="primary")
                do_delete = col_del.form_submit_button("🗑 Delete Sale")

            if do_save:
                _, sp, fp = compute_sale(e_price, e_qty, e_disc, e_gst, e_admin)
                idx = sales[sales["Sale ID"] == str(sel_id)].index[0]
                sales.at[idx, "Date"]             = str(e_d)
                sales.at[idx, "Product Code"]     = e_code
                sales.at[idx, "Product Name"]     = e_name
                sales.at[idx, "Product Price"]    = e_price
                sales.at[idx, "Customer Name"]    = e_cust
                sales.at[idx, "Customer Email"]   = e_email
                sales.at[idx, "Customer Phone"]   = e_phone
                sales.at[idx, "Order Quantity"]   = int(e_qty)
                sales.at[idx, "Discount %"]       = e_disc
                sales.at[idx, "GST %"]            = e_gst
                sales.at[idx, "Admin & General %"]= e_admin
                sales.at[idx, "GST Reclaimed"]    = e_gstr
                sales.at[idx, "Payment Status"]   = e_pays
                sales.at[idx, "Payment Date"]     = str(e_payd) if e_pays != "Pending" else "Pending"
                sales.at[idx, "Order Status"]     = e_ords
                sales.at[idx, "Delivery Date"]    = str(e_deld)
                sales.at[idx, "Sale Price"]       = sp
                sales.at[idx, "Final Sale Price"] = fp
                save(sales, SALES_FILE)
                st.success("✅ Sale updated.")
                st.rerun()

            if do_delete:
                sales = sales[sales["Sale ID"] != str(sel_id)]
                save(sales, SALES_FILE)
                st.success(f"🗑 Sale #{sel_id} deleted.")
                st.rerun()

    # ── EXPORT ───────────────────────────────────────────────────────────────
    with tab_export:
        sales = load(SALES_FILE, SALES_COLS)
        if sales.empty:
            st.info("No sales to export.")
        else:
            sales["_date_parsed"] = pd.to_datetime(sales["Date"], errors="coerce")
            sales["_month"]       = sales["_date_parsed"].dt.to_period("M").astype(str)
            months = sorted(sales["_month"].dropna().unique().tolist())
            sel_months = st.multiselect("Select Month(s) to Export", ["All"] + months, default=["All"])

            if "All" in sel_months or not sel_months:
                export_df = sales.drop(columns=["_date_parsed","_month"])
            else:
                export_df = sales[sales["_month"].isin(sel_months)].drop(columns=["_date_parsed","_month"])

            st.write(f"{len(export_df)} rows selected")
            buf = io.BytesIO()
            with pd.ExcelWriter(buf, engine="openpyxl") as writer:
                export_df.to_excel(writer, index=False, sheet_name="Sales")
            st.download_button("📥 Download Excel", buf.getvalue(),
                               file_name="sales_export.xlsx",
                               mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

# ════════════════════════════════════════════════════════════════════════════
# PAGE: INVENTORY DETAILS
# ════════════════════════════════════════════════════════════════════════════
elif page == "Inventory Details":
    st.header("Inventory Details")
    inv = load(INVENTORY_FILE, INVENTORY_COLS)

    tab_add, tab_view, tab_export = st.tabs(["➕ Add Entry", "📝 View / Edit / Delete", "📤 Export"])

    with tab_add:
        with st.form("inv_form", clear_on_submit=True):
            c1, c2 = st.columns(2)
            with c1:
                i_date  = st.date_input("Date", value=date.today())
                i_type  = st.selectbox("Cost Type", ["Flexible","Fixed"])
                i_mat   = st.text_input("Material Name")
                i_qty   = st.number_input("Quantity Purchased", min_value=0, step=1)
                i_cpu   = st.number_input("Cost per Unit (₹)", min_value=0.0, step=1.0)
            with c2:
                i_disc  = st.number_input("Discount %", 0.0, 100.0, 0.0)
                i_gst   = st.number_input("GST %", 0.0, 100.0, 6.0)
                i_gstr  = st.selectbox("GST Reclaimed?", ["Y","N"])
                i_used  = st.number_input("Raw Material Used", min_value=0, step=1)

            if st.form_submit_button("Add Entry", type="primary"):
                total = compute_material_cost(i_qty, i_cpu, i_disc, i_gst)
                row = {
                    "Entry ID": next_id(inv, "Entry ID"),
                    "Date": str(i_date), "Cost Type": i_type, "Material Name": i_mat,
                    "Quantity Purchased": int(i_qty), "Cost per Unit": i_cpu,
                    "Discount %": i_disc, "GST %": i_gst, "GST Reclaimed": i_gstr,
                    "Total Cost": total, "Raw Material Used": int(i_used),
                    "Inventory Remaining": int(i_qty) - int(i_used),
                }
                inv = pd.concat([inv, pd.DataFrame([row])], ignore_index=True)
                save(inv, INVENTORY_FILE)
                st.success(f"✅ Entry added. Total cost: ₹{total:,.2f}")
                st.rerun()

    with tab_view:
        inv = load(INVENTORY_FILE, INVENTORY_COLS)
        if inv.empty:
            st.info("No inventory entries yet.")
        else:
            st.dataframe(inv, use_container_width=True, height=300)
            st.subheader("Edit or Delete an Entry")
            inv_ids = inv["Entry ID"].tolist()
            sel_inv_id = st.selectbox("Select Entry ID", inv_ids)
            sel_inv_row = inv[inv["Entry ID"] == str(sel_inv_id)].iloc[0]

            with st.form("edit_inv_form"):
                ec1, ec2 = st.columns(2)
                with ec1:
                    ei_date = st.date_input("Date", value=pd.to_datetime(sel_inv_row["Date"], errors="coerce") or date.today())
                    ei_type = st.selectbox("Cost Type", ["Flexible","Fixed"],
                                           index=0 if sel_inv_row["Cost Type"]=="Flexible" else 1)
                    ei_mat  = st.text_input("Material Name", value=sel_inv_row["Material Name"])
                    ei_qty  = st.number_input("Quantity Purchased", value=int(float(sel_inv_row["Quantity Purchased"] or 0)), step=1)
                    ei_cpu  = st.number_input("Cost per Unit", value=float(sel_inv_row["Cost per Unit"] or 0))
                with ec2:
                    ei_disc = st.number_input("Discount %", value=float(sel_inv_row["Discount %"] or 0))
                    ei_gst  = st.number_input("GST %", value=float(sel_inv_row["GST %"] or 0))
                    ei_gstr = st.selectbox("GST Reclaimed?", ["Y","N"],
                                           index=0 if sel_inv_row["GST Reclaimed"]=="Y" else 1)
                    ei_used = st.number_input("Raw Material Used", value=int(float(sel_inv_row["Raw Material Used"] or 0)), step=1)

                col_save2, col_del2 = st.columns(2)
                do_save2   = col_save2.form_submit_button("💾 Save Changes", type="primary")
                do_delete2 = col_del2.form_submit_button("🗑 Delete Entry")

            if do_save2:
                total2 = compute_material_cost(ei_qty, ei_cpu, ei_disc, ei_gst)
                idx2 = inv[inv["Entry ID"] == str(sel_inv_id)].index[0]
                inv.at[idx2, "Date"]               = str(ei_date)
                inv.at[idx2, "Cost Type"]          = ei_type
                inv.at[idx2, "Material Name"]      = ei_mat
                inv.at[idx2, "Quantity Purchased"] = int(ei_qty)
                inv.at[idx2, "Cost per Unit"]      = ei_cpu
                inv.at[idx2, "Discount %"]         = ei_disc
                inv.at[idx2, "GST %"]              = ei_gst
                inv.at[idx2, "GST Reclaimed"]      = ei_gstr
                inv.at[idx2, "Total Cost"]         = total2
                inv.at[idx2, "Raw Material Used"]  = int(ei_used)
                inv.at[idx2, "Inventory Remaining"]= int(ei_qty) - int(ei_used)
                save(inv, INVENTORY_FILE)
                st.success("✅ Entry updated.")
                st.rerun()

            if do_delete2:
                inv = inv[inv["Entry ID"] != str(sel_inv_id)]
                save(inv, INVENTORY_FILE)
                st.success("🗑 Entry deleted.")
                st.rerun()

    with tab_export:
        inv = load(INVENTORY_FILE, INVENTORY_COLS)
        if inv.empty:
            st.info("No inventory to export.")
        else:
            inv["_date_parsed"] = pd.to_datetime(inv["Date"], errors="coerce")
            inv["_month"]       = inv["_date_parsed"].dt.to_period("M").astype(str)
            i_months = sorted(inv["_month"].dropna().unique().tolist())
            sel_i_months = st.multiselect("Select Month(s)", ["All"] + i_months, default=["All"])
            if "All" in sel_i_months or not sel_i_months:
                exp_inv = inv.drop(columns=["_date_parsed","_month"])
            else:
                exp_inv = inv[inv["_month"].isin(sel_i_months)].drop(columns=["_date_parsed","_month"])
            buf2 = io.BytesIO()
            with pd.ExcelWriter(buf2, engine="openpyxl") as writer:
                exp_inv.to_excel(writer, index=False, sheet_name="Inventory")
            st.download_button("📥 Download Excel", buf2.getvalue(),
                               file_name="inventory_export.xlsx",
                               mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

# ════════════════════════════════════════════════════════════════════════════
# PAGE: WORKER & TASK SETUP
# ════════════════════════════════════════════════════════════════════════════
elif page == "Worker & Task Setup":
    st.header("Worker & Task Setup")
    workers = load(WORKERS_FILE, WORKERS_COLS)
    tasks   = load(TASKS_FILE,   TASKS_COLS)

    col_w, col_t = st.columns(2)

    with col_w:
        st.subheader("👷 Workers")
        with st.form("worker_form", clear_on_submit=True):
            w_name = st.text_input("Worker Name")
            w_act  = st.selectbox("Primary Activity", ACTIVITIES)
            w_act2 = st.multiselect("Also handles", [a for a in ACTIVITIES if a != w_act])
            if st.form_submit_button("Add Worker", type="primary"):
                all_acts = [w_act] + w_act2
                for act in all_acts:
                    row = {"Worker ID": next_id(workers, "Worker ID"),
                           "Worker Name": w_name, "Activity": act, "Active": "Y"}
                    workers = pd.concat([workers, pd.DataFrame([row])], ignore_index=True)
                save(workers, WORKERS_FILE)
                st.success(f"✅ Worker '{w_name}' added for {', '.join(all_acts)}")
                st.rerun()

        if not workers.empty:
            st.dataframe(workers, use_container_width=True)
            del_wid = st.selectbox("Delete Worker ID", workers["Worker ID"].tolist(), key="del_w")
            if st.button("🗑 Delete Worker"):
                workers = workers[workers["Worker ID"] != str(del_wid)]
                save(workers, WORKERS_FILE)
                st.rerun()

    with col_t:
        st.subheader("💰 Task Rates (per bag, per activity)")
        with st.form("task_form", clear_on_submit=True):
            t_code = st.text_input("Product Code")
            t_name = st.text_input("Product Name")
            t_act  = st.selectbox("Activity", ACTIVITIES)
            t_rate = st.number_input("Rate per Unit (₹)", min_value=0.0, step=1.0)
            if st.form_submit_button("Set Rate", type="primary"):
                mask = (tasks["Product Code"] == t_code) & (tasks["Activity"] == t_act)
                if mask.any():
                    tasks.loc[mask, "Rate per Unit"] = t_rate
                    tasks.loc[mask, "Product Name"]  = t_name
                else:
                    row = {"Task ID": next_id(tasks,"Task ID"),
                           "Product Code": t_code, "Product Name": t_name,
                           "Activity": t_act, "Rate per Unit": t_rate}
                    tasks = pd.concat([tasks, pd.DataFrame([row])], ignore_index=True)
                save(tasks, TASKS_FILE)
                st.success(f"✅ Rate set: {t_code} / {t_act} = ₹{t_rate}/unit")
                st.rerun()

        if not tasks.empty:
            pivot = tasks.pivot_table(index="Product Name", columns="Activity",
                                      values="Rate per Unit", aggfunc="first")
            st.dataframe(pivot.fillna("—"), use_container_width=True)

# ════════════════════════════════════════════════════════════════════════════
# PAGE: PRODUCTIVITY / WORKERS
# ════════════════════════════════════════════════════════════════════════════
elif page == "Productivity / Workers":
    st.header("Worker Productivity Log")
    workers  = load(WORKERS_FILE,  WORKERS_COLS)
    tasks    = load(TASKS_FILE,    TASKS_COLS)
    work_log = load(WORK_LOG_FILE, WORK_LOG_COLS)

    tab_add, tab_view, tab_export = st.tabs(["➕ Log Work", "📝 View / Edit / Delete", "📤 Export"])

    with tab_add:
        if workers.empty:
            st.warning("⚠️ Add workers first in **Worker & Task Setup**.")
        elif tasks.empty:
            st.warning("⚠️ Add task rates first in **Worker & Task Setup**.")
        else:
            with st.form("work_form", clear_on_submit=True):
                wc1, wc2 = st.columns(2)
                with wc1:
                    w_date = st.date_input("Date", value=date.today())
                    worker_options = workers.drop_duplicates("Worker Name")["Worker Name"].tolist()
                    w_worker = st.selectbox("Worker", worker_options)
                    worker_acts = workers[workers["Worker Name"]==w_worker]["Activity"].tolist()
                    w_act_sel = st.selectbox("Activity", worker_acts)
                    avail_tasks = tasks[tasks["Activity"]==w_act_sel]
                    if avail_tasks.empty:
                        st.warning("No task rates set for this activity. Set them in Worker & Task Setup.")
                        prod_options = []
                    else:
                        prod_options = (avail_tasks["Product Code"] + " – " + avail_tasks["Product Name"]).tolist()

                    w_prod_sel = st.selectbox("Product", prod_options, disabled=(len(prod_options) == 0))
                with wc2:
                    w_units = st.number_input("Units Done", min_value=0, step=1)

                submitted = st.form_submit_button("Submit", type="primary")

                if submitted and prod_options:
                    prod_code = w_prod_sel.split(" – ")[0]
                    prod_name = w_prod_sel.split(" – ", 1)[1] if " – " in w_prod_sel else w_prod_sel
                    rate_row  = tasks[(tasks["Product Code"]==prod_code) & (tasks["Activity"]==w_act_sel)]
                    rate      = float(rate_row["Rate per Unit"].iloc[0]) if not rate_row.empty else 0
                    earnings  = round(rate * w_units, 2)
                    wid       = workers[workers["Worker Name"]==w_worker]["Worker ID"].iloc[0]
                    row = {
                        "Log ID": next_id(work_log,"Log ID"),
                        "Date": str(w_date), "Worker ID": wid, "Worker Name": w_worker,
                        "Activity": w_act_sel, "Product Code": prod_code,
                        "Product Name": prod_name, "Units Done": int(w_units),
                        "Rate per Unit": rate, "Earnings": earnings,
                    }
                    work_log = pd.concat([work_log, pd.DataFrame([row])], ignore_index=True)
                    save(work_log, WORK_LOG_FILE)
                    st.success(f"✅ Logged {w_units} units for {w_worker} — Earnings: ₹{earnings:,.2f}")
                    st.rerun()

    with tab_view:
        work_log = load(WORK_LOG_FILE, WORK_LOG_COLS)
        if work_log.empty:
            st.info("No work logged yet.")
        else:
            st.dataframe(work_log, use_container_width=True, height=300)
            st.subheader("Edit or Delete a Log Entry")
            log_ids = work_log["Log ID"].tolist()
            sel_log = st.selectbox("Select Log ID", log_ids)
            sel_log_row = work_log[work_log["Log ID"]==str(sel_log)].iloc[0]
            with st.form("edit_log_form"):
                el1, el2 = st.columns(2)
                with el1:
                    el_date  = st.date_input("Date", value=pd.to_datetime(sel_log_row["Date"], errors="coerce") or date.today())
                    el_units = st.number_input("Units Done", value=int(float(sel_log_row["Units Done"] or 0)), step=1)
                    el_rate  = st.number_input("Rate per Unit", value=float(sel_log_row["Rate per Unit"] or 0))
                col_s, col_d = st.columns(2)
                do_s = col_s.form_submit_button("💾 Save", type="primary")
                do_d = col_d.form_submit_button("🗑 Delete")

            if do_s:
                idx_l = work_log[work_log["Log ID"]==str(sel_log)].index[0]
                work_log.at[idx_l,"Date"]         = str(el_date)
                work_log.at[idx_l,"Units Done"]   = int(el_units)
                work_log.at[idx_l,"Rate per Unit"] = el_rate
                work_log.at[idx_l,"Earnings"]     = round(el_rate * el_units, 2)
                save(work_log, WORK_LOG_FILE)
                st.success("✅ Log updated.")
                st.rerun()
            if do_d:
                work_log = work_log[work_log["Log ID"]!=str(sel_log)]
                save(work_log, WORK_LOG_FILE)
                st.success("🗑 Log deleted.")
                st.rerun()

    with tab_export:
        work_log = load(WORK_LOG_FILE, WORK_LOG_COLS)
        if work_log.empty:
            st.info("Nothing to export.")
        else:
            work_log["_month"] = pd.to_datetime(work_log["Date"], errors="coerce").dt.to_period("M").astype(str)
            wl_months = sorted(work_log["_month"].dropna().unique().tolist())
            sel_wl_months = st.multiselect("Select Month(s)", ["All"] + wl_months, default=["All"])
            if "All" in sel_wl_months or not sel_wl_months:
                exp_wl = work_log.drop(columns=["_month"])
            else:
                exp_wl = work_log[work_log["_month"].isin(sel_wl_months)].drop(columns=["_month"])
            buf3 = io.BytesIO()
            with pd.ExcelWriter(buf3, engine="openpyxl") as writer:
                exp_wl.to_excel(writer, index=False, sheet_name="WorkLog")
            st.download_button("📥 Download Excel", buf3.getvalue(),
                               file_name="work_log_export.xlsx",
                               mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

# ════════════════════════════════════════════════════════════════════════════
# ANALYSIS: TOP CUSTOMERS
# ════════════════════════════════════════════════════════════════════════════
elif page == "Top Customers":
    st.header("Top Customers")
    sales = load(SALES_FILE, SALES_COLS)
    if sales.empty:
        st.info("No sales data yet.")
    else:
        active = sales[sales["Order Status"] != "Cancelled"].copy()
        active["Final Sale Price"] = num(active, "Final Sale Price")
        active["Order Quantity"]   = num(active, "Order Quantity")

        top = (active.groupby("Customer Name", dropna=False)
               .agg(Total_Revenue=("Final Sale Price","sum"),
                    Total_Orders=("Sale ID","count"),
                    Total_Qty=("Order Quantity","sum"))
               .sort_values("Total_Revenue", ascending=False).reset_index())

        m1,m2,m3 = st.columns(3)
        m1.metric("Unique Customers", top["Customer Name"].nunique())
        if not top.empty:
            m2.metric("Top Customer", top.iloc[0]["Customer Name"])
            m3.metric("Top Revenue", fmt_inr(top.iloc[0]["Total_Revenue"]))

        fig = px.bar(top.head(10), x="Customer Name", y="Total_Revenue",
                     color="Total_Orders", title="Top 10 Customers by Revenue",
                     labels={"Total_Revenue":"Revenue (₹)","Total_Orders":"Orders"})
        st.plotly_chart(fig, use_container_width=True)
        st.dataframe(top, use_container_width=True)

# ════════════════════════════════════════════════════════════════════════════
# ANALYSIS: TOP PRODUCTS
# ════════════════════════════════════════════════════════════════════════════
elif page == "Top Products Sold":
    st.header("Top Products Sold")
    sales = load(SALES_FILE, SALES_COLS)
    if sales.empty:
        st.info("No sales data yet.")
    else:
        active = sales[sales["Order Status"] != "Cancelled"].copy()
        active["Final Sale Price"] = num(active, "Final Sale Price")
        active["Order Quantity"]   = num(active, "Order Quantity")

        by_qty = active.groupby("Product Name")["Order Quantity"].sum().sort_values(ascending=False).reset_index()
        by_rev = active.groupby("Product Name")["Final Sale Price"].sum().sort_values(ascending=False).reset_index()

        c1,c2 = st.columns(2)
        with c1:
            st.subheader("By Quantity Sold")
            fig = px.bar(by_qty, x="Product Name", y="Order Quantity",
                         title="Units Sold per Product")
            fig.update_layout(xaxis_tickangle=-35)
            st.plotly_chart(fig, use_container_width=True)
        with c2:
            st.subheader("By Revenue")
            fig2 = px.bar(by_rev, x="Product Name", y="Final Sale Price",
                          title="Revenue per Product (₹)")
            fig2.update_layout(xaxis_tickangle=-35)
            st.plotly_chart(fig2, use_container_width=True)

        cancelled = sales[sales["Order Status"]=="Cancelled"]
        if not cancelled.empty:
            st.subheader("🚫 Cancelled Orders")
            st.dataframe(cancelled[["Sale ID","Date","Customer Name","Product Name",
                                    "Order Quantity","Final Sale Price","Order Status"]],
                         use_container_width=True)

# ════════════════════════════════════════════════════════════════════════════
# ANALYSIS: MONTHLY CASHFLOW
# ════════════════════════════════════════════════════════════════════════════
elif page == "Monthly Cashflow":
    st.header("Monthly Cashflow")
    sales = load(SALES_FILE, SALES_COLS)
    inv   = load(INVENTORY_FILE, INVENTORY_COLS)

    inflow_df  = pd.DataFrame(columns=["Month","Inflow"])
    outflow_df = pd.DataFrame(columns=["Month","Outflow"])

    if not sales.empty:
        s = sales[sales["Order Status"]!="Cancelled"].copy()
        s["Final Sale Price"] = num(s,"Final Sale Price")
        s["Payment Date"]     = pd.to_datetime(s["Payment Date"], errors="coerce")
        s = s.dropna(subset=["Payment Date"])
        s["Month"] = s["Payment Date"].dt.to_period("M").astype(str)
        inflow_df = s.groupby("Month")["Final Sale Price"].sum().reset_index()
        inflow_df.columns = ["Month","Inflow"]

    if not inv.empty:
        i = inv.copy()
        i["Total Cost"] = num(i,"Total Cost")
        i["Date"]       = pd.to_datetime(i["Date"], errors="coerce")
        i = i.dropna(subset=["Date"])
        i["Month"] = i["Date"].dt.to_period("M").astype(str)
        outflow_df = i.groupby("Month")["Total Cost"].sum().reset_index()
        outflow_df.columns = ["Month","Outflow"]

    cf = pd.merge(inflow_df, outflow_df, on="Month", how="outer").fillna(0)
    cf = cf.sort_values("Month")
    cf["Net"] = cf["Inflow"] - cf["Outflow"]

    m1,m2,m3 = st.columns(3)
    m1.metric("Total Inflow",  fmt_inr(cf["Inflow"].sum()))
    m2.metric("Total Outflow", fmt_inr(cf["Outflow"].sum()))
    net = cf["Net"].sum()
    m3.metric("Net Cashflow",  fmt_inr(net))

    if not cf.empty:
        long = cf.melt(id_vars="Month", value_vars=["Inflow","Outflow"],
                       var_name="Type", value_name="Amount")
        fig = px.bar(long, x="Month", y="Amount", color="Type", barmode="group",
                     title="Monthly Cashflow",
                     color_discrete_map={"Inflow":"#2c6e49","Outflow":"#e63946"})
        st.plotly_chart(fig, use_container_width=True)

        fig2 = px.line(cf, x="Month", y="Net", title="Net Cashflow Trend",
                       markers=True, color_discrete_sequence=["#457b9d"])
        fig2.add_hline(y=0, line_dash="dash", line_color="red")
        st.plotly_chart(fig2, use_container_width=True)
        st.dataframe(cf, use_container_width=True)

# ════════════════════════════════════════════════════════════════════════════
# ANALYSIS: FIXED vs FLEXIBLE
# ════════════════════════════════════════════════════════════════════════════
elif page == "Fixed vs Flexible Expenses":
    st.header("Fixed vs Flexible Expenses")
    inv = load(INVENTORY_FILE, INVENTORY_COLS)
    if inv.empty:
        st.info("No inventory data yet.")
    else:
        inv["Total Cost"] = num(inv,"Total Cost")
        by_type = inv.groupby("Cost Type")["Total Cost"].sum().reset_index()
        by_mat  = (inv.groupby(["Cost Type","Material Name"])["Total Cost"]
                   .sum().reset_index().sort_values("Total Cost", ascending=False))

        c1,c2 = st.columns(2)
        with c1:
            fig = px.pie(by_type, names="Cost Type", values="Total Cost",
                         title="Fixed vs Flexible Share",
                         color_discrete_map={"Fixed":"#e63946","Flexible":"#2c6e49"})
            st.plotly_chart(fig, use_container_width=True)
        with c2:
            fig2 = px.bar(by_mat, x="Material Name", y="Total Cost", color="Cost Type",
                          title="Cost per Material",
                          color_discrete_map={"Fixed":"#e63946","Flexible":"#2c6e49"})
            fig2.update_layout(xaxis_tickangle=-35)
            st.plotly_chart(fig2, use_container_width=True)
        st.dataframe(by_mat, use_container_width=True)

# ════════════════════════════════════════════════════════════════════════════
# ANALYSIS: WORKER PRODUCTIVITY & PROFIT SHARE
# ════════════════════════════════════════════════════════════════════════════
elif page == "Worker Productivity & Profit Share":
    st.header("Worker Productivity & Profit Share")
    work_log = load(WORK_LOG_FILE, WORK_LOG_COLS)
    sales    = load(SALES_FILE,    SALES_COLS)

    if work_log.empty:
        st.info("No work logged yet. Log work in **Productivity / Workers**.")
    else:
        work_log["Units Done"] = num(work_log,"Units Done")
        work_log["Earnings"]   = num(work_log,"Earnings")

        st.subheader("Per-Worker Summary")
        by_worker = work_log.groupby("Worker Name").agg(
            Units_Done=("Units Done","sum"),
            Total_Earnings=("Earnings","sum"),
            Activities=("Activity", lambda x: ", ".join(sorted(x.unique()))),
        ).reset_index().sort_values("Total_Earnings", ascending=False)

        fig = px.bar(by_worker, x="Worker Name", y="Total_Earnings",
                     title="Total Earnings per Worker (₹)",
                     color="Total_Earnings", color_continuous_scale="Greens")
        st.plotly_chart(fig, use_container_width=True)
        st.dataframe(by_worker, use_container_width=True)

        st.subheader("Per-Activity Summary")
        by_act = work_log.groupby("Activity").agg(
            Total_Units=("Units Done","sum"),
            Total_Cost=("Earnings","sum"),
        ).reset_index()
        fig2 = px.pie(by_act, names="Activity", values="Total_Cost",
                      title="Labour Cost by Activity")
        st.plotly_chart(fig2, use_container_width=True)

        st.subheader("Labour Cost per Product")
        by_prod = work_log.groupby(["Product Name","Activity"]).agg(
            Total_Units=("Units Done","sum"),
            Total_Cost=("Earnings","sum"),
        ).reset_index()
        fig3 = px.bar(by_prod, x="Product Name", y="Total_Cost", color="Activity",
                      title="Labour Cost per Product by Activity (₹)", barmode="stack")
        fig3.update_layout(xaxis_tickangle=-35)
        st.plotly_chart(fig3, use_container_width=True)

        st.subheader("Proportional Profit Share from Sales")
        if not sales.empty:
            active_sales = sales[sales["Order Status"]!="Cancelled"].copy()
            active_sales["Final Sale Price"] = num(active_sales,"Final Sale Price")
            total_revenue = active_sales["Final Sale Price"].sum()
            total_labour  = work_log["Earnings"].sum()
            gross_profit  = total_revenue - total_labour

            col_r1, col_r2, col_r3 = st.columns(3)
            col_r1.metric("Total Revenue",    fmt_inr(total_revenue))
            col_r2.metric("Total Labour Cost", fmt_inr(total_labour))
            col_r3.metric("Gross Profit",      fmt_inr(gross_profit))

            if total_labour > 0:
                by_worker["Share %"]          = (by_worker["Total_Earnings"] / total_labour * 100).round(2)
                by_worker["Revenue Share (₹)"] = (by_worker["Total_Earnings"] / total_labour * total_revenue).round(2)
            else:
                by_worker["Share %"]          = 0
                by_worker["Revenue Share (₹)"] = 0

            st.dataframe(by_worker[["Worker Name","Activities","Units_Done",
                                    "Total_Earnings","Share %","Revenue Share (₹)"]],
                         use_container_width=True)

            st.subheader("Monthly Earnings per Worker")
            work_log["Month"] = pd.to_datetime(work_log["Date"], errors="coerce").dt.to_period("M").astype(str)
            monthly = work_log.groupby(["Month","Worker Name"])["Earnings"].sum().reset_index()
            fig4 = px.line(monthly, x="Month", y="Earnings", color="Worker Name",
                           title="Monthly Earnings per Worker (₹)", markers=True)
            st.plotly_chart(fig4, use_container_width=True)

# ════════════════════════════════════════════════════════════════════════════
# ANALYSIS: INVENTORY STATUS
# ════════════════════════════════════════════════════════════════════════════
elif page == "Inventory Status":
    st.header("Inventory Status")
    inv  = load(INVENTORY_FILE,  INVENTORY_COLS)
    prod = load(PRODUCTION_FILE, PRODUCTION_COLS)

    st.subheader("Raw Materials Remaining")
    if inv.empty:
        st.info("No raw material data.")
    else:
        inv["Inventory Remaining"] = num(inv,"Inventory Remaining")
        inv["Total Cost"]          = num(inv,"Total Cost")
        mat = inv.groupby("Material Name").agg(
            Remaining=("Inventory Remaining","sum"),
            Total_Cost=("Total Cost","sum"),
        ).reset_index()
        low = mat[mat["Remaining"] <= 2]
        if not low.empty:
            st.warning(f"⚠️ Low stock: {', '.join(low['Material Name'].tolist())}")
        fig = px.bar(mat, x="Material Name", y="Remaining",
                     color="Remaining", color_continuous_scale="RdYlGn",
                     title="Raw Material Inventory")
        fig.update_layout(xaxis_tickangle=-35)
        st.plotly_chart(fig, use_container_width=True)
        st.dataframe(mat, use_container_width=True)

    st.subheader("Finished Product Inventory")
    if prod.empty:
        st.info("No production data.")
    else:
        prod["Inventory of Products"] = num(prod,"Inventory of Products")
        finished = prod.groupby("Product Name")["Inventory of Products"].sum().reset_index()
        fig2 = px.bar(finished, x="Product Name", y="Inventory of Products",
                      title="Finished Product Stock")
        fig2.update_layout(xaxis_tickangle=-35)
        st.plotly_chart(fig2, use_container_width=True)
        st.dataframe(finished, use_container_width=True)

# ════════════════════════════════════════════════════════════════════════════
# INVOICE GENERATOR
# ════════════════════════════════════════════════════════════════════════════
elif page == "Generate Invoice":
    st.header("🧾 Invoice Generator")
    sales = load(SALES_FILE, SALES_COLS)

    tab_existing, tab_custom = st.tabs(["From a Sale Record", "Custom / Blank Invoice"])

    with tab_existing:
        if sales.empty:
            st.info("No sales recorded yet.")
        else:
            sale_options = sales.apply(
                lambda r: f"#{r['Sale ID']} — {r['Customer Name']} — {r['Product Name']} ({r['Date']})", axis=1
            ).tolist()
            sel_sale_label = st.selectbox("Select Sale", sale_options)
            sel_sale_idx   = sale_options.index(sel_sale_label)
            sale_row       = sales.iloc[sel_sale_idx].to_dict()

            with st.expander("📋 Sale Details", expanded=True):
                dc1,dc2 = st.columns(2)
                dc1.write(f"**Customer:** {sale_row['Customer Name']}")
                dc1.write(f"**Product:** {sale_row['Product Name']} ({sale_row['Product Code']})")
                dc1.write(f"**Qty:** {sale_row['Order Quantity']} × ₹{sale_row['Product Price']}")
                dc2.write(f"**Discount:** {sale_row['Discount %']}%  |  **GST:** {sale_row['GST %']}%")
                dc2.write(f"**Admin & General:** {sale_row['Admin & General %']}%")
                dc2.write(f"**Final Sale Price:** ₹{sale_row['Final Sale Price']}")
                dc2.write(f"**Order Status:** {sale_row['Order Status']}")

            if st.button("🖨️ Generate Invoice PDF", type="primary"):
                pdf_bytes = generate_invoice_pdf(sale_row)
                inv_no    = f"INV-{sale_row['Sale ID']}"
                st.download_button(
                    label=f"📥 Download {inv_no}.pdf",
                    data=pdf_bytes,
                    file_name=f"{inv_no}.pdf",
                    mime="application/pdf",
                )
                st.success("Invoice ready — click the button above to download and print.")

    with tab_custom:
        st.subheader("Create a custom invoice")
        with st.form("custom_inv_form"):
            ci1,ci2 = st.columns(2)
            with ci1:
                ci_id    = st.text_input("Invoice / Reference No.", value="CUSTOM-001")
                ci_date  = st.date_input("Date", value=date.today())
                ci_cust  = st.text_input("Customer Name")
                ci_email = st.text_input("Customer Email")
                ci_phone = st.text_input("Customer Phone")
            with ci2:
                ci_code  = st.text_input("Product Code")
                ci_name  = st.text_input("Product Name")
                ci_price = st.number_input("Unit Price (₹)", min_value=0.0, step=10.0)
                ci_qty   = st.number_input("Quantity", min_value=1, step=1)
                ci_disc  = st.number_input("Discount %", 0.0, 100.0, 0.0)
                ci_gst   = st.number_input("GST %", 0.0, 100.0, 6.0)
                ci_admin = st.number_input("Admin & General %", 0.0, 100.0, 10.0)
                ci_pay   = st.selectbox("Payment Status", PAY_STATUSES)
                ci_ords  = st.selectbox("Order Status", ORDER_STATUSES)
                ci_deld  = st.date_input("Delivery Date", value=date.today())

            if st.form_submit_button("Generate Custom Invoice", type="primary"):
                custom_row = {
                    "Sale ID": ci_id, "Date": str(ci_date),
                    "Customer Name": ci_cust, "Customer Email": ci_email,
                    "Customer Phone": ci_phone, "Product Code": ci_code,
                    "Product Name": ci_name, "Product Price": ci_price,
                    "Order Quantity": ci_qty, "Discount %": ci_disc,
                    "GST %": ci_gst, "Admin & General %": ci_admin,
                    "Payment Status": ci_pay, "Payment Date": str(date.today()),
                    "Order Status": ci_ords, "Delivery Date": str(ci_deld),
                }
                pdf_bytes2 = generate_invoice_pdf(custom_row)
                st.download_button(
                    label=f"📥 Download {ci_id}.pdf",
                    data=pdf_bytes2,
                    file_name=f"{ci_id}.pdf",
                    mime="application/pdf",
                )
                st.success("Custom invoice ready.")
