import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime, date, timedelta
import plotly.express as px
from sklearn.linear_model import LinearRegression
import numpy as np
import smtplib
from email.mime.text import MIMEText
import bcrypt
import os

# Session State
# ───────────────────────────────────────────────
if 'user_email' not in st.session_state:
    st.session_state.user_email = None
if 'user_name' not in st.session_state:
    st.session_state.user_name = ""
if 'theme' not in st.session_state:
    st.session_state.theme = "Light"
if 'smtp_email' not in st.session_state:
    st.session_state.smtp_email = ""
if 'smtp_app_password' not in st.session_state:
    st.session_state.smtp_app_password = ""
if 'currency' not in st.session_state:
    st.session_state.currency = "INR"
if 'conv_rate' not in st.session_state:
    st.session_state.conv_rate = 1.0

CURRENCIES = {"INR": "₹", "USD": "$", "EUR": "€"}
RECEIPTS_DIR = "receipts"
os.makedirs(RECEIPTS_DIR, exist_ok=True)

CATEGORIES = ["Food", "Transport", "Rent/Bills", "Entertainment", "Shopping", "Other"]
INCOME_SOURCES = ["Salary", "Freelance", "Gift", "Other"]

# ───────────────────────────────────────────────
# Database - safe & complete
# ───────────────────────────────────────────────
def init_db():
    conn = sqlite3.connect('tracker.db')
    c = conn.cursor()

    # Users
    c.execute('''CREATE TABLE IF NOT EXISTS users (
        email TEXT PRIMARY KEY,
        name TEXT,
        password_hash TEXT
    )''')

    # Add 'name' column if missing (fixes old DB error)
    c.execute("PRAGMA table_info(users)")
    columns = [col[1] for col in c.fetchall()]
    if 'name' not in columns:
        c.execute("ALTER TABLE users ADD COLUMN name TEXT")
        c.execute("UPDATE users SET name = 'User' WHERE name IS NULL")

    # Expenses
    c.execute('''CREATE TABLE IF NOT EXISTS expenses (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_email TEXT,
        date TEXT,
        category TEXT,
        amount REAL,
        description TEXT,
        receipt_path TEXT,
        is_recurring INTEGER DEFAULT 0,
        frequency TEXT,
        next_date TEXT,
        deleted_at TEXT
    )''')

    # Incomes
    c.execute('''CREATE TABLE IF NOT EXISTS incomes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_email TEXT,
        date TEXT,
        source TEXT,
        amount REAL,
        description TEXT
    )''')

    # Category budgets
    c.execute('''CREATE TABLE IF NOT EXISTS category_budgets (
        month_year TEXT,
        category TEXT,
        amount REAL,
        PRIMARY KEY (month_year, category)
    )''')

    conn.commit()
    conn.close()

init_db()

# ───────────────────────────────────────────────
# Helpers
# ───────────────────────────────────────────────
def get_conn():
    return sqlite3.connect('tracker.db')

current_month = datetime.now().strftime("%Y-%m")

def symbol():
    return CURRENCIES.get(st.session_state.currency, "₹")

def convert(amt):
    return amt * st.session_state.get('conv_rate', 1.0)

def send_alert(subject, body):
    if not st.session_state.smtp_email or not st.session_state.smtp_app_password:
        return
    try:
        msg = MIMEText(body)
        msg['Subject'] = subject
        msg['From'] = st.session_state.smtp_email
        msg['To'] = st.session_state.user_email
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(st.session_state.smtp_email, st.session_state.smtp_app_password)
            server.send_message(msg)
    except:
        pass

# ───────────────────────────────────────────────
# Auth
# ───────────────────────────────────────────────
def hash_pw(pw):
    return bcrypt.hashpw(pw.encode(), bcrypt.gensalt()).decode()

def check_pw(pw, h):
    return bcrypt.checkpw(pw.encode(), h.encode())

def signup(name, email, pw):
    email = email.lower().strip()
    if not name or not email or not pw:
        return False, "Fill all fields"
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT email FROM users WHERE email = ?", (email,))
    if c.fetchone():
        conn.close()
        return False, "Email taken"
    h = hash_pw(pw)
    c.execute("INSERT INTO users VALUES (?, ?, ?)", (email, name, h))
    conn.commit()
    conn.close()
    return True, "Account created"

def login(email, pw):
    email = email.lower().strip()
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT password_hash, name FROM users WHERE email = ?", (email,))
    row = c.fetchone()
    conn.close()
    if row and check_pw(pw, row[0]):
        st.session_state.user_name = row[1] or "User"
        return True, email
    return False, None

def reset_password(email, new_pw):
    email = email.lower().strip()
    if not new_pw:
        return False, "New password required"
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT email FROM users WHERE email = ?", (email,))
    if not c.fetchone():
        conn.close()
        return False, "Email not found"
    h = hash_pw(new_pw)
    c.execute("UPDATE users SET password_hash = ? WHERE email = ?", (h, email))
    conn.commit()
    conn.close()
    return True, "Password reset successfully"


# ───────────────────────────────────────────────
# Login / Signup / Forgot Password
# ───────────────────────────────────────────────
if st.session_state.user_email is None:
    st.set_page_config(page_title="Tracker • Login", layout="centered")
    st.title("Expense & Income Tracker 💰")
    st.markdown("Sign in or create your account to start tracking your expense ")

    tab1, tab2, tab3 = st.tabs(["Login", "Sign Up", "Forgot Password"])

    with tab1:
        with st.form("login_form", clear_on_submit=False):
            email = st.text_input("Email", placeholder="example@gmail.com", key="login_email")
            pw = st.text_input("Password", type="password", placeholder="••••••••", key="login_pw")

            if st.form_submit_button("Login", use_container_width=True):
                if not email or not pw:
                    st.error("Please fill both email and password")
                else:
                    ok, user = login(email, pw)
                    if ok:
                        st.session_state.user_email = user
                        st.success("Login successful! Redirecting...")
                        st.rerun()
                    else:
                        st.error("Invalid email or password. Try again.")

    with tab2:
        with st.form("signup_form", clear_on_submit=True):
            name = st.text_input("Full Name", placeholder="Your Name", key="signup_name")
            email = st.text_input("Email", placeholder="example@gmail.com", key="signup_email")
            pw = st.text_input("Password", type="password", placeholder="••••••••", key="signup_pw")
            pw_confirm = st.text_input("Confirm Password", type="password", placeholder="••••••••",
                                       key="signup_pw_confirm")

            if st.form_submit_button("Create Account", use_container_width=True):
                if not name or not email or not pw:
                    st.error("Please fill all fields")
                elif pw != pw_confirm:
                    st.error("Passwords do not match")
                elif len(pw) < 6:
                    st.error("Password must be at least 6 characters")
                else:
                    ok, msg = signup(name, email, pw)
                    if ok:
                        st.session_state.user_email = email
                        st.session_state.user_name = name
                        st.success(msg + " — Logging you in automatically...")
                        st.rerun()
                    else:
                        st.error(msg)

    with tab3:
        with st.form("forgot_form", clear_on_submit=True):
            email = st.text_input("Your Email", placeholder="example@gmail.com", key="forgot_email")
            new_pw = st.text_input("New Password", type="password", placeholder="New password", key="forgot_new_pw")
            new_pw_confirm = st.text_input("Confirm New Password", type="password", placeholder="Confirm",
                                           key="forgot_confirm")

            if st.form_submit_button("Reset Password", use_container_width=True):
                if not email or not new_pw:
                    st.error("Please fill email and new password")
                elif new_pw != new_pw_confirm:
                    st.error("Passwords do not match")
                elif len(new_pw) < 6:
                    st.error("Password must be at least 6 characters")
                else:
                    ok, msg = reset_password(email, new_pw)
                    if ok:
                        st.success(msg + " — You can now login with the new password")
                    else:
                        st.error(msg)

    st.stop()

# Main App
# ───────────────────────────────────────────────
st.set_page_config(page_title="Tracker", layout="wide")

if st.session_state.theme == "Dark":
    st.markdown("<style>.stApp {background:#0e1117; color:white}</style>", unsafe_allow_html=True)

st.sidebar.title("Tracker")
st.sidebar.markdown(f"**Welcome, {st.session_state.user_name or 'User'}** 👤")
st.sidebar.markdown(f"({st.session_state.user_email})")

# Sidebar with beautiful emojis
page = st.sidebar.radio("Go to", [
    "Dashboard",
    "Your Income",
    "Your Expenses",
    "Set Budgets",
    "Manage Entries",
    "Trash",
    "Charts",
    "Prediction",
    "Settings"
])

if st.sidebar.button(" Logout"):
    st.session_state.user_email = None
    st.session_state.user_name = ""
    st.rerun()

# ───────────────────────────────────────────────
# Dashboard - with best category display format
# ───────────────────────────────────────────────
if page == "Dashboard":
    st.title(f"Welcome back, {st.session_state.user_name or 'User'}! ")
    # Auto-process recurring transactions (runs every time Dashboard opens)
    today = date.today().isoformat()
    conn = get_conn()
    c = conn.cursor()

    # Expenses recurring
    c.execute("SELECT * FROM expenses WHERE user_email = ? AND is_recurring = 1 AND next_date <= ? AND deleted_at IS NULL",
              (st.session_state.user_email, today))
    exp_rows = c.fetchall()

    for row in exp_rows:
        # Create new entry for this month
        c.execute("""
            INSERT INTO expenses (user_email, date, category, amount, description, receipt_path, is_recurring, frequency, next_date)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (st.session_state.user_email, today, row[3], row[4], row[5], row[6], 1, "Monthly",
              (datetime.fromisoformat(row[9]) + timedelta(days=30)).isoformat()))

    # Incomes recurring (if you added recurring to income table)
    c.execute("SELECT * FROM incomes WHERE user_email = ? AND is_recurring = 1 AND next_date <= ?",
              (st.session_state.user_email, today))
    inc_rows = c.fetchall()

    for row in inc_rows:
        c.execute("""
            INSERT INTO incomes (user_email, date, source, amount, description, is_recurring, frequency, next_date)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (st.session_state.user_email, today, row[3], row[4], row[5], 1, "Monthly",
              (datetime.fromisoformat(row[8]) + timedelta(days=30)).isoformat()))

    if exp_rows or inc_rows:
        conn.commit()
        st.toast(f"Auto-added {len(exp_rows)} recurring expenses & {len(inc_rows)} incomes! ")

    conn.close()

    conn = get_conn()
    exp_total = pd.read_sql_query(
        "SELECT SUM(amount) as s FROM expenses WHERE user_email = ? AND deleted_at IS NULL",
        conn, params=(st.session_state.user_email,)
    )['s'].iloc[0] or 0

    inc_total = pd.read_sql_query(
        "SELECT SUM(amount) as s FROM incomes WHERE user_email = ?",
        conn, params=(st.session_state.user_email,)
    )['s'].iloc[0] or 0

    conn.close()

    savings = inc_total - exp_total

    cols = st.columns(3)
    cols[0].metric("Income", f"{symbol()}{convert(inc_total):,.2f}")
    cols[1].metric("Expenses", f"{symbol()}{convert(exp_total):,.2f}")
    cols[2].metric("Savings", f"{symbol()}{convert(savings):,.2f}")

    # ───────────────────────────────────────────────
    # Category Budget Progress - BEST format you wanted
    # ───────────────────────────────────────────────
    st.subheader("Category Budget Progress")

    conn = get_conn()
    budgets = pd.read_sql_query(
        "SELECT category, amount FROM category_budgets WHERE month_year = ?",
        conn, params=(current_month,)
    )
    conn.close()

    if budgets.empty:
        st.info("No budgets set yet. Go to ' Set Budgets' to add some!")
    else:
        for _, b in budgets.iterrows():
            cat = b['category']
            budget = b['amount'] or 0
            spent = pd.read_sql_query(
                "SELECT SUM(amount) as s FROM expenses WHERE user_email = ? AND category = ? AND deleted_at IS NULL AND strftime('%Y-%m', date) = ?",
                get_conn(), params=(st.session_state.user_email, cat, current_month)
            )['s'].iloc[0] or 0

            remaining = budget - spent
            percentage_used = (spent / budget * 100) if budget > 0 else 0
            percentage_under = 100 - percentage_used if budget > 0 else 0

            # Status text & color
            if budget == 0:
                status = "No budget set"
                color = "grey"
            elif percentage_used > 100:
                status = f"{abs(percentage_under):.0f}% **over** budget "
                color = "error"
            elif percentage_used > 80:
                status = f"{percentage_under:.0f}% under budget (warning zone)"
                color = "warning"
            else:
                status = f"{percentage_under:.0f}% under budget "
                color = "success"

            # Beautiful display
            st.markdown(f"**{cat}**")
            st.caption(f"Spent: {symbol()}{convert(spent):,.0f} of {symbol()}{convert(budget):,.0f} budget")
            st.caption(f"**{status}**")

            # Progress bar (shows how much used)
            prog_value = min(percentage_used / 100, 1.0)
            st.progress(prog_value, text=f"{percentage_used:.0f}% used")

            # Remaining or over
            if remaining > 0:
                st.success(f"Remaining: {symbol()}{convert(remaining):,.0f} ")
            elif remaining < 0:
                st.error(f"Over by: {symbol()}{convert(-remaining):,.0f}  ️")
                send_alert("Budget Alert", f"{cat}: over by {symbol()}{convert(-remaining):,.2f}")
            else:
                st.warning("Budget fully used")

            st.markdown("---")  # nice separator line

# ───────────────────────────────────────────────
# Set Budgets
# ───────────────────────────────────────────────
elif page == "Set Budgets":
    st.title("Set Category Budgets")
    month_date = st.date_input("Month", value=date.today().replace(day=1))
    month = month_date.strftime("%Y-%m")

    for cat in CATEGORIES:
        amt = st.number_input(f"Budget for {cat} ({symbol()})", min_value=0.0, step=500.0, value=0.0)
        if st.button(f"Save {cat}"):
            conn = get_conn()
            c = conn.cursor()
            c.execute("INSERT OR REPLACE INTO category_budgets VALUES (?, ?, ?)", (month, cat, amt))
            conn.commit()
            conn.close()
            st.success(f"Budget for {cat} saved for {month}")

# ───────────────────────────────────────────────
# Your Expenses
# ───────────────────────────────────────────────
elif page == "Your Expenses":
    st.title("Add New Expense")
    d = st.date_input("Date", date.today())
    cat = st.selectbox("Category", CATEGORIES)
    amt = st.number_input("Amount", min_value=0.0, step=1.0)
    desc = st.text_input("Description")
    rec = st.checkbox("Repeat every month? (recurring) ")
    if rec:
        st.info("This expense will auto-repeat every month")
    rec = st.checkbox("Mark as Recurring?")
    freq = st.selectbox("Frequency", ["Monthly", "Weekly"]) if rec else None
    receipt = st.file_uploader("Receipt (optional)", type=["jpg", "png"])

    if st.button("Add Expense"):
        if amt <= 0 or d > date.today():
            st.error("Invalid input")
        else:
            path = None
            if receipt:
                path = os.path.join(RECEIPTS_DIR, f"{st.session_state.user_email}_{receipt.name}")
                with open(path, "wb") as f:
                    f.write(receipt.getvalue())

            next_date = None
            if rec:
                # Next month same date
                next_d = datetime.combine(d, datetime.min.time()) + timedelta(days=30)
                next_date = next_d.isoformat()

            conn = get_conn()
            c = conn.cursor()
            c.execute("""
                INSERT INTO expenses (user_email, date, category, amount, description, receipt_path, is_recurring, frequency, next_date)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (st.session_state.user_email, d.isoformat(), cat, amt, desc, path, 1 if rec else 0, "Monthly" if rec else None, next_date))
            conn.commit()
            conn.close()
            st.success("Expense added!" + (" (will repeat monthly )" if rec else ""))

# ───────────────────────────────────────────────
# Your Income
# ───────────────────────────────────────────────
elif page == "Your Income":
    st.title("Add New Income")
    d = st.date_input("Date", date.today())
    src = st.selectbox("Source", INCOME_SOURCES)
    amt = st.number_input("Amount", min_value=0.0, step=1.0)
    desc = st.text_input("Description")
    rec = st.checkbox("Repeat monthly? (recurring) ")
    if rec:
        st.info("This income will auto-repeat every month on the same date")

    if st.button("Add Income"):
        if amt <= 0:
            st.error("Amount must be > 0")
        else:
            next_date = None
            if rec:
                next_d = datetime.combine(d, datetime.min.time()) + timedelta(days=30)
                next_date = next_d.isoformat()

            conn = get_conn()
            c = conn.cursor()
            c.execute("""
                INSERT INTO incomes (user_email, date, source, amount, description, is_recurring, frequency, next_date)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (st.session_state.user_email, d.isoformat(), src, amt, desc, 1 if rec else 0, "Monthly" if rec else None, next_date))
            conn.commit()
            conn.close()
            st.success("Income added!" + (" (will repeat monthly )" if rec else ""))

# ───────────────────────────────────────────────
# Manage Entries
# ───────────────────────────────────────────────
elif page == "Manage Entries":
    st.title("Manage Entries")

    tab1, tab2 = st.tabs(["Expenses", "Incomes"])

    with tab1:
        search = st.text_input(" Search description")
        from_d = st.date_input("From", date.today().replace(day=1))
        to_d = st.date_input("To", date.today())

        conn = get_conn()
        q = "SELECT id, date, category, amount, description, receipt_path FROM expenses WHERE user_email = ? AND deleted_at IS NULL"
        p = [st.session_state.user_email]
        if search:
            q += " AND description LIKE ?"
            p.append(f"%{search}%")
        if from_d:
            q += " AND date >= ?"
            p.append(from_d.isoformat())
        if to_d:
            q += " AND date <= ?"
            p.append(to_d.isoformat())
        df = pd.read_sql_query(q, conn, params=p)
        conn.close()

        if not df.empty:
            st.dataframe(df[['id','date','category','amount','description']])
            csv = df.to_csv(index=False).encode()
            st.download_button(" Export Expenses CSV", csv, "expenses.csv", "text/csv")

            eid = st.number_input("ID to Edit/Delete", step=1)
            row = df[df['id'] == eid]
            if not row.empty:
                row = row.iloc[0]
                new_d = st.date_input("New Date", pd.to_datetime(row['date']))
                new_cat = st.selectbox("New Category", CATEGORIES, index=CATEGORIES.index(row['category']))
                new_amt = st.number_input("New Amount", value=float(row['amount']), min_value=0.01)
                new_desc = st.text_input("New Description", value=row['description'] or "")

                col_a, col_b = st.columns(2)
                with col_a:
                    if st.button("️ Update"):
                        conn = get_conn()
                        c = conn.cursor()
                        c.execute("UPDATE expenses SET date=?, category=?, amount=?, description=? WHERE id=?",
                                  (new_d.isoformat(), new_cat, new_amt, new_desc, eid))
                        conn.commit()
                        conn.close()
                        st.success("Expense updated")

                with col_b:
                    if st.button("🗑 Delete"):
                        conn = get_conn()
                        c = conn.cursor()
                        c.execute("UPDATE expenses SET deleted_at = ? WHERE id = ?", (datetime.now().isoformat(), eid))
                        conn.commit()
                        conn.close()
                        st.success("Moved to trash")

                if row['receipt_path'] and os.path.exists(row['receipt_path']):
                    st.subheader("Receipt Preview")
                    st.image(row['receipt_path'], width=400)
        else:
            st.info("No expenses match the filter")

    with tab2:
        search_inc = st.text_input(" Search description/source")
        conn = get_conn()
        q_inc = "SELECT id, date, source, amount, description FROM incomes WHERE user_email = ?"
        p_inc = [st.session_state.user_email]
        if search_inc:
            q_inc += " AND (description LIKE ? OR source LIKE ?)"
            p_inc.extend([f"%{search_inc}%", f"%{search_inc}%"])
        df_inc = pd.read_sql_query(q_inc, conn, params=p_inc)
        conn.close()

        if not df_inc.empty:
            st.dataframe(df_inc)
            csv_inc = df_inc.to_csv(index=False).encode()
            st.download_button(" Export Incomes CSV", csv_inc, "incomes.csv", "text/csv")

            iid = st.number_input("ID to Edit/Delete (Income)", step=1)
            row_inc = df_inc[df_inc['id'] == iid]
            if not row_inc.empty:
                row_inc = row_inc.iloc[0]
                new_d = st.date_input("New Date", pd.to_datetime(row_inc['date']))
                new_src = st.selectbox("New Source", INCOME_SOURCES, index=INCOME_SOURCES.index(row_inc['source']))
                new_amt = st.number_input("New Amount", value=float(row_inc['amount']), min_value=0.01)
                new_desc = st.text_input("New Description", value=row_inc['description'] or "")

                col_a, col_b = st.columns(2)
                with col_a:
                    if st.button("️ Update Income"):
                        conn = get_conn()
                        c = conn.cursor()
                        c.execute("UPDATE incomes SET date=?, source=?, amount=?, description=? WHERE id=?",
                                  (new_d.isoformat(), new_src, new_amt, new_desc, iid))
                        conn.commit()
                        conn.close()
                        st.success("Income updated")

                with col_b:
                    if st.button("️ Delete Income"):
                        conn = get_conn()
                        c = conn.cursor()
                        c.execute("DELETE FROM incomes WHERE id = ?", (iid,))
                        conn.commit()
                        conn.close()
                        st.success("Income deleted")
        else:
            st.info("No incomes match the filter")

# ───────────────────────────────────────────────
# Trash
# ───────────────────────────────────────────────
elif page == "Trash":
    st.title("Trash (Deleted Expenses)")
    st.caption("Items you deleted from expenses appear here. You can restore or permanently delete them.")

    conn = get_conn()
    df = pd.read_sql_query(
        "SELECT id, date, category, amount, description FROM expenses WHERE user_email = ? AND deleted_at IS NOT NULL ORDER BY deleted_at DESC",
        conn, params=(st.session_state.user_email,)
    )
    conn.close()

    if df.empty:
        st.info("Trash is empty. Delete some expenses from 'Manage Entries' to see them here.")
    else:
        st.dataframe(df)
        tid = st.number_input("Enter ID to restore or delete", step=1, min_value=0)

        if tid in df['id'].values:
            col1, col2 = st.columns(2)
            with col1:
                if st.button("Restore", key=f"restore_{tid}"):
                    conn = get_conn()
                    c = conn.cursor()
                    c.execute("UPDATE expenses SET deleted_at = NULL WHERE id = ?", (tid,))
                    conn.commit()
                    conn.close()
                    st.success(f"Item {tid} restored!")
                    st.rerun()

            with col2:
                if st.button("Permanent Delete", key=f"perm_delete_{tid}"):
                    conn = get_conn()
                    c = conn.cursor()
                    c.execute("DELETE FROM expenses WHERE id = ?", (tid,))
                    conn.commit()
                    conn.close()
                    st.success(f"Item {tid} deleted forever!")
                    st.rerun()
        else:
            if tid > 0:
                st.warning(f"ID {tid} not found in trash")
# ───────────────────────────────────────────────
# Charts
# ───────────────────────────────────────────────
elif page == "Charts":
    st.title("Charts & Trends ")
    conn = get_conn()
    df = pd.read_sql_query("SELECT date, category, amount FROM expenses WHERE user_email = ? AND deleted_at IS NULL", conn, params=(st.session_state.user_email,))
    conn.close()
    if df.empty:
        st.info("No expenses yet to show charts")
    else:
        df['date'] = pd.to_datetime(df['date'])
        st.subheader("Expense by Category (Pie)")
        fig_pie = px.pie(df, values='amount', names='category')
        st.plotly_chart(fig_pie, use_container_width=True)
        st.subheader("Monthly Trend (Bar)")
        df['month'] = df['date'].dt.strftime('%Y-%m')
        monthly = df.groupby('month')['amount'].sum().reset_index()
        fig_bar = px.bar(monthly, x='month', y='amount')
        st.plotly_chart(fig_bar, use_container_width=True)
        st.subheader("Daily Spending Trend (Line)")
        daily = df.groupby('date')['amount'].sum().reset_index()
        fig_line = px.line(daily, x='date', y='amount')
        st.plotly_chart(fig_line, use_container_width=True)

# ───────────────────────────────────────────────
# Prediction
# ───────────────────────────────────────────────
elif page == "Prediction":
    st.title("Next Month Expense Prediction")
    conn = get_conn()
    df = pd.read_sql_query("SELECT date, amount FROM expenses WHERE user_email = ? AND deleted_at IS NULL", conn, params=(st.session_state.user_email,))
    conn.close()
    if len(df) < 3:
        st.info("Need at least 3 months of data for prediction")
    else:
        df['date'] = pd.to_datetime(df['date'])
        df['month'] = df['date'].dt.to_period('M')
        monthly = df.groupby('month')['amount'].sum().reset_index()
        monthly['num'] = range(len(monthly))
        if len(monthly) >= 3:
            X = monthly[['num']]
            y = monthly['amount']
            model = LinearRegression().fit(X, y)
            pred = model.predict([[len(monthly)]])[0]
            st.success(f"Predicted next month expense: {symbol()}{max(0, pred):,.2f}")
        else:
            st.info("Need more months for better prediction")

# ───────────────────────────────────────────────
# Settings
# ───────────────────────────────────────────────
elif page == "Settings":
    st.title("Settings")

    # Theme
    st.subheader("Theme")
    th = st.radio("Choose theme", ["Light", "Dark"], index=0 if st.session_state.theme == "Light" else 1,
                  horizontal=True)
    if th != st.session_state.theme:
        st.session_state.theme = th
        st.rerun()

    # Currency
    st.subheader("Currency")
    cur = st.selectbox("Select currency", list(CURRENCIES.keys()),
                       index=list(CURRENCIES.keys()).index(st.session_state.currency))
    if cur != st.session_state.currency:
        st.session_state.currency = cur
        st.success(f"Currency changed to {cur}")

    # Conversion Rate
    st.subheader("Conversion Rate")
    rate = st.number_input("Rate (1 base = X display)", min_value=0.01, value=st.session_state.conv_rate, step=0.01)
    if st.button("Apply Rate"):
        st.session_state.conv_rate = rate
        st.success("Conversion rate updated!")

    # Email Alerts
    st.subheader("Email Alerts (for over-budget)")
    em = st.text_input("Your Gmail", value=st.session_state.smtp_email)
    pw = st.text_input("Gmail App Password", type="password", value=st.session_state.smtp_app_password)

    col1, col2 = st.columns(2)
    with col1:
        if st.button("Save Email Settings"):
            st.session_state.smtp_email = em.strip()
            st.session_state.smtp_app_password = pw.strip()
            st.success("Email settings saved!")

    with col2:
        if st.button("Send Test Email"):
            if st.session_state.smtp_email and st.session_state.smtp_app_password:
                send_alert("Test Alert", "This is a test message from your tracker!")
                st.success("Test email sent! Check your inbox/spam.")
            else:
                st.error("Please save Gmail and App Password first")

# Clean footer
st.sidebar.caption("")