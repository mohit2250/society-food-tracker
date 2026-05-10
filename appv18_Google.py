import streamlit as st
import pandas as pd
from datetime import datetime
from streamlit_gsheets import GSheetsConnection

# --- DATABASE SETUP (CLOUD VERSION) ---
# This creates a connection using the URL you will provide in "Secrets"
conn = st.connection("gsheets", type=GSheetsConnection)

def load_data(sheet_name="cashbook"):
    try:
        # ttl=0 ensures it doesn't show old data from cache
        return conn.read(worksheet=sheet_name, ttl=0)
    except Exception as e:
        # If sheet is empty, return empty dataframe with correct headers
        return pd.DataFrame(columns=["Date", "Type", "Particulars", "Cash_In", "Cash_Out", "Qty", "Rate", "Location", "Item"])

def save_data(new_entry_df, sheet_name="cashbook"):
    existing_df = load_data(sheet_name)
    # Combine old data with the new entry
    updated_df = pd.concat([existing_df, new_entry_df], ignore_index=True)
    # Write back to Google Sheets
    conn.update(worksheet=sheet_name, data=updated_df)
    st.cache_data.clear() # Clear memory so it shows the new row immediately

# --- SMART MEMORY HELPERS ---
def get_clean_suggestions(col_name, filter_type=None):
    df = load_data("cashbook")
    if not df.empty:
        if filter_type:
            df = df[df['Type'] == filter_type]
        vals = df[col_name].unique().tolist()
        return sorted([str(x) for x in vals if x and x not in ["Cash", "Deposit"]])
    return []

def get_stock(fruit, location):
    df = load_data("cashbook")
    if df.empty: return 0
    in_purch = df[(df['Type'] == "Purchase") & (df['Item'] == fruit) & (df['Location'] == location)]['Qty'].sum()
    in_trans = df[(df['Type'] == "Transfer") & (df['Item'] == fruit) & (df['Location'] == location)]['Qty'].sum()
    out_sale = df[(df['Type'] == "Sale") & (df['Item'] == fruit) & (df['Location'] == location)]['Qty'].sum()
    out_trans = df[(df['Type'] == "Transfer Out") & (df['Item'] == fruit) & (df['Location'] == location)]['Qty'].sum()
    return (in_purch + in_trans) - (out_sale + out_trans)

# --- APP CONFIG ---
st.set_page_config(layout="wide", page_title="Society ERP Pro", page_icon="🍏")
st.title("🍏 Society Smart Management System")

menu = ["📊 Dashboard", "💰 Balance & Edits", "🛒 Purchases", "🚛 Stock Movement", "🗳️ Sector Sales", "💸 Expenses", "📦 Delivery Deposits", "📓 Full Cash Book"]
choice = st.sidebar.selectbox("Main Menu", menu)

# --- 1. BALANCE & EDITS ---
if choice == "💰 Balance & Edits":
    st.header("Financial Adjustments & Correction Center")
    tab1, tab2 = st.tabs(["💰 Add/Adjust Cash", "🛠️ Rename Mistyped Items/Sectors"])
    with tab1:
        with st.form("bal_form"):
            d, desc, amt = st.date_input("Date"), st.text_input("Particulars"), st.number_input("Amount", min_value=0.0)
            act = st.radio("Action", ["Cash In", "Cash Out"])
            if st.form_submit_button("Update Balance"):
                v_in, v_out = (amt, 0) if act == "Cash In" else (0, amt)
                save_data(pd.DataFrame([[str(d), "Adjustment", desc, v_in, v_out, 0, 0, "Master", "Cash"]], 
                         columns=["Date", "Type", "Particulars", "Cash_In", "Cash_Out", "Qty", "Rate", "Location", "Item"]), "cashbook")
                st.success("Balance updated!")
    with tab2:
        st.subheader("Rename Any Entry Globally")
        col_to_fix = st.selectbox("Type of item to fix", ["Item", "Location", "Particulars"])
        wrong_name, correct_name = st.text_input("Incorrect Name"), st.text_input("Correct Name")
        if st.button("Fix All Records"):
            df = load_data("cashbook")
            if not df.empty and wrong_name and correct_name:
                df[col_to_fix] = df[col_to_fix].replace(wrong_name, correct_name)
                df.to_sql("cashbook", engine, if_exists="replace", index=False)
                st.success("Updated!")
                st.rerun()

# --- 2. PURCHASES ---
elif choice == "🛒 Purchases":
    st.header("Bulk Procurement")
    fruits = get_clean_suggestions("Item")
    with st.form("p_form", clear_on_submit=True):
        d = st.date_input("Date")
        f = st.selectbox("Existing Fruit", ["New Item"] + fruits)
        f_new, q, r, s = st.text_input("If New, type here"), st.number_input("Qty"), st.number_input("Rate"), st.text_input("Supplier")
        if st.form_submit_button("Save Purchase"):
            final_f = f_new if f == "New Item" else f
            save_data(pd.DataFrame([[str(d), "Purchase", f"Bought {final_f} from {s}", 0, q*r, q, r, "Master", final_f]], 
                     columns=["Date", "Type", "Particulars", "Cash_In", "Cash_Out", "Qty", "Rate", "Location", "Item"]), "cashbook")
            st.success("Recorded!"); st.rerun()

# --- 3. STOCK MOVEMENT ---
elif choice == "🚛 Stock Movement":
    st.header("Move Stock")
    fruits, sectors = get_clean_suggestions("Item"), get_clean_suggestions("Location")
    f, frm = st.selectbox("Select Fruit", fruits), st.selectbox("From Location", ["Master"] + sectors)
    avail = get_stock(f, frm)
    st.info(f"Available: {avail} kg")
    with st.form("move_form"):
        d, to = st.date_input("Date"), st.selectbox("To Sector", ["New Sector"] + sectors)
        to_new, q = st.text_input("If New, type here"), st.number_input("Qty")
        if st.form_submit_button("Transfer"):
            if q > avail: st.error("Low Stock!")
            else:
                final_to = to_new if to == "New Sector" else to
                save_data(pd.DataFrame([[str(d), "Transfer Out", f"To {final_to}", 0, 0, q, 0, frm, f]], columns=["Date", "Type", "Particulars", "Cash_In", "Cash_Out", "Qty", "Rate", "Location", "Item"]), "cashbook")
                save_data(pd.DataFrame([[str(d), "Transfer", f"From {frm}", 0, 0, q, 0, final_to, f]], columns=["Date", "Type", "Particulars", "Cash_In", "Cash_Out", "Qty", "Rate", "Location", "Item"]), "cashbook")
                st.success("Moved!")

# --- 4. SECTOR SALES ---
elif choice == "🗳️ Sector Sales":
    st.header("Daily Sales Entry")
    fruits, sectors = get_clean_suggestions("Item"), get_clean_suggestions("Location")
    f, sec = st.selectbox("Select Fruit", fruits), st.selectbox("Selling Sector", sectors)
    avail = get_stock(f, sec)
    st.warning(f"Stock at {sec}: {avail} kg")
    with st.form("sale_form"):
        d, q, r = st.date_input("Date"), st.number_input("Qty Sold"), st.number_input("Price")
        if st.form_submit_button("Record Sale"):
            if q > avail: st.error("Insufficient Stock!")
            else:
                save_data(pd.DataFrame([[str(d), "Sale", f"Sold {f} @ {sec}", q*r, 0, q, r, sec, f]], columns=["Date", "Type", "Particulars", "Cash_In", "Cash_Out", "Qty", "Rate", "Location", "Item"]), "cashbook")
                st.success("Sale Logged!")

# --- 5. EXPENSES ---
elif choice == "💸 Expenses":
    st.header("Log Expenses")
    exp_history = get_clean_suggestions("Particulars", filter_type="Expense")
    with st.form("ex_form"):
        d, det_opt = st.date_input("Date"), st.selectbox("Past Expense Categories", ["New Expense"] + exp_history)
        det_new, amt = st.text_input("Type Expense Detail if New"), st.number_input("Amount")
        if st.form_submit_button("Save"):
            final_det = det_new if det_opt == "New Expense" else det_opt
            save_data(pd.DataFrame([[str(d), "Expense", final_det, 0, amt, 0, 0, "Master", "Cash"]], columns=["Date", "Type", "Particulars", "Cash_In", "Cash_Out", "Qty", "Rate", "Location", "Item"]), "cashbook")
            st.success("Expense Logged!")

# --- 6. DELIVERY DEPOSITS ---
elif choice == "📦 Delivery Deposits":
    st.header("Home Delivery Deposits")
    with st.form("dep_form"):
        d, mem, amt = st.date_input("Date"), st.text_input("Member/House"), st.number_input("Amount")
        act = st.radio("Type", ["Collected", "Refunded"])
        if st.form_submit_button("Record"):
            v_in, v_out = (amt, 0) if "Collected" in act else (0, amt)
            save_data(pd.DataFrame([[str(d), "Deposit", f"{act}: {mem}", v_in, v_out, 0, 0, "Master", "Deposit"]], columns=["Date", "Type", "Particulars", "Cash_In", "Cash_Out", "Qty", "Rate", "Location", "Item"]), "cashbook")
            st.success("Deposit Recorded")

# --- 7. CASH BOOK ---
elif choice == "📓 Full Cash Book":
    st.header("Master History")
    df = load_data("cashbook")
    if not df.empty:
        df['Balance'] = df['Cash_In'].cumsum() - df['Cash_Out'].cumsum()
        st.dataframe(df); idx = st.number_input("Index to Delete", 0, len(df)-1)
        if st.button("Delete Row"):
            df = df.drop(df.index[idx]).to_sql("cashbook", engine, if_exists="replace", index=False); st.rerun()

# --- 8. DASHBOARD (RESTORED FILTERS & TABLE) ---
elif choice == "📊 Dashboard":
    df = load_data("cashbook")
    if not df.empty:
        st.sidebar.header("Dashboard Filters")
        f_date = st.sidebar.date_input("Filter by Date", value=None)
        f_fruit = st.sidebar.selectbox("Filter Fruit", ["All"] + get_clean_suggestions("Item"))
        f_loc = st.sidebar.selectbox("Filter Sector", ["All"] + get_clean_suggestions("Location"))
        
        c1, c2, c3 = st.columns(3)
        c1.metric("💰 Cash Balance", f"₹{(df['Cash_In'].sum() - df['Cash_Out'].sum()):,.2f}")
        c2.metric("📈 Revenue", f"₹{df[df['Type']=='Sale']['Cash_In'].sum():,.2f}")
        c3.metric("🍎 Total Sold", f"{df[df['Type']=='Sale']['Qty'].sum()} kg")

        st.divider()
        st.subheader("📦 Live Stock Balance")
        items, locs = get_clean_suggestions("Item"), ["Master"] + get_clean_suggestions("Location")
        stock_list = []
        for it in items:
            for l in locs:
                stk = get_stock(it, l)
                if stk != 0: stock_list.append({"Item": it, "Location": l, "Stock (kg)": stk})
        if stock_list:
            stock_df = pd.DataFrame(stock_list)
            if f_fruit != "All": stock_df = stock_df[stock_df['Item'] == f_fruit]
            if f_loc != "All": stock_df = stock_df[stock_df['Location'] == f_loc]
            st.table(stock_df)

        st.divider()
        st.subheader("📊 Sales Data & Trends")
        sales_df = df[df['Type'] == "Sale"].copy()
        if f_date: sales_df = sales_df[sales_df['Date'].dt.date == f_date]
        if f_fruit != "All": sales_df = sales_df[sales_df['Item'] == f_fruit]
        if f_loc != "All": sales_df = sales_df[sales_df['Location'] == f_loc]
        
        st.write("Recent Sales List:")
        st.dataframe(sales_df[['Date', 'Location', 'Item', 'Qty', 'Rate', 'Cash_In']])
        
        st.write("Daily Cash Flow:")
        chart_data = df.groupby('Date')[['Cash_In', 'Cash_Out']].sum()
        st.line_chart(chart_data)
