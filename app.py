from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st

from auth import hash_password, verify_password
from db import execute, execute_returning, fetch_all, fetch_one

st.set_page_config(
    page_title="Personal Finance Simulation Platform",
    page_icon="💰",
    layout="wide",
)


# -----------------------------
# Helpers
# -----------------------------

def show_table(rows, empty_message="No records found."):
    if rows:
        st.dataframe(pd.DataFrame(rows), use_container_width=True)
    else:
        st.info(empty_message)


def login_user(email: str, password: str) -> bool:
    user = fetch_one(
        """
        SELECT user_id, email, full_name, role, base_currency, password_hash
        FROM app_user
        WHERE lower(email) = lower(%s) AND is_active = TRUE
        """,
        (email,),
    )
    if user and verify_password(password, user["password_hash"]):
        user.pop("password_hash", None)
        st.session_state["user"] = dict(user)
        return True
    return False


def current_user():
    return st.session_state.get("user")


def is_admin() -> bool:
    user = current_user()
    return bool(user and user["role"] == "admin")


def user_selector_for_reports() -> int:
    user = current_user()
    if not is_admin():
        return int(user["user_id"])
    users = fetch_all(
        "SELECT user_id, full_name, email FROM app_user WHERE is_active = TRUE ORDER BY user_id"
    )
    options = {f'{u["full_name"]} ({u["email"]})': int(u["user_id"]) for u in users}
    selected_label = st.selectbox("Report user", list(options.keys()), index=0, key="report_user_select")
    return options[selected_label]


def get_user_accounts(user_id: int):
    if is_admin():
        return fetch_all(
            """
            SELECT a.account_id, u.full_name, a.account_name, a.account_type,
                   a.current_balance, a.currency_code, fi.institution_name
            FROM account a
            JOIN app_user u ON u.user_id = a.user_id
            LEFT JOIN financial_institution fi ON fi.institution_id = a.institution_id
            ORDER BY a.account_id
            """
        )
    return fetch_all(
        """
        SELECT a.account_id, a.account_name, a.account_type,
               a.current_balance, a.currency_code, fi.institution_name
        FROM account a
        LEFT JOIN financial_institution fi ON fi.institution_id = a.institution_id
        WHERE a.user_id = %s
        ORDER BY a.account_id
        """,
        (user_id,),
    )


def user_options():
    users = fetch_all("SELECT user_id, full_name, email FROM app_user WHERE is_active = TRUE ORDER BY user_id")
    return {f'{u["full_name"]} ({u["email"]})': int(u["user_id"]) for u in users}


def category_options(category_type: str | None = None):
    if category_type:
        rows = fetch_all(
            "SELECT category_id, category_name FROM category WHERE category_type = %s ORDER BY category_name",
            (category_type,),
        )
    else:
        rows = fetch_all("SELECT category_id, category_name FROM category ORDER BY category_name")
    return {r["category_name"]: int(r["category_id"]) for r in rows}


def merchant_options():
    rows = fetch_all("SELECT merchant_id, merchant_name FROM merchant ORDER BY merchant_name")
    return {r["merchant_name"]: int(r["merchant_id"]) for r in rows}


def account_options(user_id: int):
    if is_admin():
        rows = fetch_all(
            """
            SELECT a.account_id, u.full_name, a.account_name
            FROM account a JOIN app_user u ON u.user_id = a.user_id
            ORDER BY a.account_id
            """
        )
        return {f'{r["account_name"]} - {r["full_name"]}': int(r["account_id"]) for r in rows}
    rows = fetch_all(
        "SELECT account_id, account_name FROM account WHERE user_id = %s ORDER BY account_id",
        (user_id,),
    )
    return {r["account_name"]: int(r["account_id"]) for r in rows}


# -----------------------------
# Screens
# -----------------------------

def login_screen():
    st.title("Personal Finance Simulation & Forecasting Platform")
    st.caption("Phase 2 demonstration application")

    with st.form("login_form"):
        email = st.text_input("Email", value="admin@example.com")
        password = st.text_input("Password", value="admin123", type="password")
        submitted = st.form_submit_button("Login")
    if submitted:
        try:
            if login_user(email, password):
                st.rerun()
            else:
                st.error("Invalid login.")
        except Exception as exc:
            st.error("The database is not ready or the connection string is incorrect.")
            st.code(str(exc))
            st.info("Run sql/final_database_dump.sql first, then configure .streamlit/secrets.toml.")

    st.markdown("""
    **Demo users**
    - Admin: `admin@example.com` / `admin123`
    - Standard user: `alex@example.com` / `user123`
    """)


def dashboard_screen():
    user = current_user()
    st.header("Dashboard")
    st.write(f"Logged in as **{user['full_name']}** ({user['role']}).")

    if is_admin():
        metrics = fetch_one(
            """
            SELECT
                (SELECT COUNT(*) FROM app_user WHERE is_active = TRUE) AS users,
                (SELECT COUNT(*) FROM account) AS accounts,
                (SELECT COUNT(*) FROM finance_transaction) AS transactions,
                (SELECT COALESCE(SUM(current_balance), 0) FROM account) AS total_balance
            """
        )
    else:
        metrics = fetch_one(
            """
            SELECT
                (SELECT COUNT(*) FROM account WHERE user_id = %s) AS accounts,
                (SELECT COUNT(*) FROM finance_transaction WHERE user_id = %s) AS transactions,
                (SELECT COALESCE(SUM(current_balance), 0) FROM account WHERE user_id = %s) AS total_balance,
                (SELECT COALESCE(SUM(amount_total), 0)
                   FROM finance_transaction
                  WHERE user_id = %s
                    AND transaction_type = 'expense'
                    AND transaction_date >= date_trunc('month', CURRENT_DATE)) AS this_month_spending
            """,
            (user["user_id"], user["user_id"], user["user_id"], user["user_id"]),
        )

    c1, c2, c3, c4 = st.columns(4)
    if is_admin():
        c1.metric("Users", metrics.get("users", 0))
        c2.metric("Accounts", metrics.get("accounts", 0))
        c3.metric("Transactions", metrics.get("transactions", 0))
        c4.metric("Total balance", f"{metrics.get('total_balance', 0):,.2f}")
    else:
        c1.metric("My accounts", metrics.get("accounts", 0))
        c2.metric("My transactions", metrics.get("transactions", 0))
        c3.metric("Total balance", f"{metrics.get('total_balance', 0):,.2f}")
        c4.metric("This month spending", f"{metrics.get('this_month_spending', 0):,.2f}")

    st.subheader("Recent transactions")
    if is_admin():
        rows = fetch_all(
            """
            SELECT t.transaction_id, u.full_name, a.account_name, c.category_name,
                   m.merchant_name, t.transaction_date, t.transaction_type, t.amount_total
            FROM finance_transaction t
            JOIN app_user u ON u.user_id = t.user_id
            JOIN account a ON a.account_id = t.account_id
            LEFT JOIN category c ON c.category_id = t.category_id
            LEFT JOIN merchant m ON m.merchant_id = t.merchant_id
            ORDER BY t.transaction_date DESC, t.transaction_id DESC
            LIMIT 20
            """
        )
    else:
        rows = fetch_all(
            """
            SELECT t.transaction_id, a.account_name, c.category_name,
                   m.merchant_name, t.transaction_date, t.transaction_type, t.amount_total
            FROM finance_transaction t
            JOIN account a ON a.account_id = t.account_id
            LEFT JOIN category c ON c.category_id = t.category_id
            LEFT JOIN merchant m ON m.merchant_id = t.merchant_id
            WHERE t.user_id = %s
            ORDER BY t.transaction_date DESC, t.transaction_id DESC
            LIMIT 20
            """,
            (user["user_id"],),
        )
    show_table(rows)


def accounts_screen():
    user = current_user()
    st.header("Accounts CRUD")

    institutions = fetch_all("SELECT institution_id, institution_name FROM financial_institution ORDER BY institution_name")
    institution_map = {r["institution_name"]: int(r["institution_id"]) for r in institutions}

    with st.expander("Create account", expanded=True):
        with st.form("create_account"):
            selected_user_id = int(user["user_id"])
            if is_admin():
                users = user_options()
                selected_user_id = users[st.selectbox("Owner", list(users.keys()))]
            institution_id = institution_map[st.selectbox("Institution", list(institution_map.keys()))]
            account_name = st.text_input("Account name")
            account_type = st.selectbox("Account type", ["checking", "savings", "credit", "investment"])
            balance = st.number_input("Current balance", min_value=-100000.0, max_value=1000000.0, value=0.0, step=100.0)
            currency = st.text_input("Currency", value="USD", max_chars=3)
            submitted = st.form_submit_button("Create account")
        if submitted:
            execute(
                """
                INSERT INTO account (user_id, institution_id, account_name, account_type, current_balance, currency_code)
                VALUES (%s, %s, %s, %s, %s, upper(%s))
                """,
                (selected_user_id, institution_id, account_name, account_type, balance, currency),
            )
            st.success("Account created.")
            st.rerun()

    rows = get_user_accounts(int(user["user_id"]))
    st.subheader("Read accounts")
    show_table(rows)

    account_map = account_options(int(user["user_id"]))
    if account_map:
        st.subheader("Update or delete account")
        selected_account_id = account_map[st.selectbox("Select account", list(account_map.keys()), key="account_update_select")]
        existing = fetch_one("SELECT * FROM account WHERE account_id = %s", (selected_account_id,))
        col1, col2 = st.columns(2)
        with col1:
            with st.form("update_account"):
                new_name = st.text_input("New account name", value=existing["account_name"])
                new_type = st.selectbox(
                    "New account type",
                    ["checking", "savings", "credit", "investment"],
                    index=["checking", "savings", "credit", "investment"].index(existing["account_type"]),
                )
                new_balance = st.number_input("New current balance", value=float(existing["current_balance"]), step=100.0)
                update_clicked = st.form_submit_button("Update account")
            if update_clicked:
                execute(
                    "UPDATE account SET account_name = %s, account_type = %s, current_balance = %s WHERE account_id = %s",
                    (new_name, new_type, new_balance, selected_account_id),
                )
                st.success("Account updated.")
                st.rerun()
        with col2:
            st.warning("Deleting an account also deletes its transactions in this demo database.")
            if st.button("Delete selected account"):
                execute("DELETE FROM account WHERE account_id = %s", (selected_account_id,))
                st.success("Account deleted.")
                st.rerun()


def transactions_screen():
    user = current_user()
    st.header("Transactions CRUD")

    accounts = account_options(int(user["user_id"]))
    categories = category_options()
    merchants = merchant_options()

    if not accounts:
        st.warning("Create at least one account before creating transactions.")
        return

    with st.expander("Create transaction", expanded=True):
        with st.form("create_transaction"):
            account_id = accounts[st.selectbox("Account", list(accounts.keys()))]
            category_id = categories[st.selectbox("Category", list(categories.keys()))]
            merchant_id = merchants[st.selectbox("Merchant", list(merchants.keys()))]
            transaction_date = st.date_input("Transaction date", value=date.today())
            transaction_type = st.selectbox("Transaction type", ["expense", "income", "transfer"])
            amount = st.number_input("Amount", min_value=0.01, max_value=100000.0, value=50.0, step=10.0)
            description = st.text_input("Description", value="Manual entry")
            submitted = st.form_submit_button("Create transaction")
        if submitted:
            owner = fetch_one("SELECT user_id FROM account WHERE account_id = %s", (account_id,))
            owner_id = int(owner["user_id"])
            if not is_admin() and owner_id != int(user["user_id"]):
                st.error("You cannot add transactions to another user's account.")
            else:
                execute(
                    """
                    INSERT INTO finance_transaction
                    (user_id, account_id, merchant_id, category_id, transaction_date, transaction_type, amount_total, description)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (owner_id, account_id, merchant_id, category_id, transaction_date, transaction_type, amount, description),
                )
                st.success("Transaction created.")
                st.rerun()

    st.subheader("Read transactions")
    if is_admin():
        rows = fetch_all(
            """
            SELECT t.transaction_id, u.full_name, a.account_name, c.category_name,
                   m.merchant_name, t.transaction_date, t.transaction_type, t.amount_total, t.description
            FROM finance_transaction t
            JOIN app_user u ON u.user_id = t.user_id
            JOIN account a ON a.account_id = t.account_id
            LEFT JOIN category c ON c.category_id = t.category_id
            LEFT JOIN merchant m ON m.merchant_id = t.merchant_id
            ORDER BY t.transaction_date DESC, t.transaction_id DESC
            LIMIT 100
            """
        )
    else:
        rows = fetch_all(
            """
            SELECT t.transaction_id, a.account_name, c.category_name,
                   m.merchant_name, t.transaction_date, t.transaction_type, t.amount_total, t.description
            FROM finance_transaction t
            JOIN account a ON a.account_id = t.account_id
            LEFT JOIN category c ON c.category_id = t.category_id
            LEFT JOIN merchant m ON m.merchant_id = t.merchant_id
            WHERE t.user_id = %s
            ORDER BY t.transaction_date DESC, t.transaction_id DESC
            LIMIT 100
            """,
            (user["user_id"],),
        )
    show_table(rows)

    st.subheader("Update or delete transaction")
    editable = rows[:50]
    if editable:
        tx_map = {f'{r["transaction_id"]} - {r.get("merchant_name", "") or "No merchant"} - {r["amount_total"]}': int(r["transaction_id"]) for r in editable}
        tx_id = tx_map[st.selectbox("Select transaction", list(tx_map.keys()))]
        existing = fetch_one("SELECT * FROM finance_transaction WHERE transaction_id = %s", (tx_id,))
        col1, col2 = st.columns(2)
        with col1:
            with st.form("update_transaction"):
                new_amount = st.number_input("New amount", min_value=0.01, value=float(existing["amount_total"]), step=10.0)
                new_description = st.text_input("New description", value=existing.get("description") or "")
                update_clicked = st.form_submit_button("Update transaction")
            if update_clicked:
                execute(
                    "UPDATE finance_transaction SET amount_total = %s, description = %s WHERE transaction_id = %s",
                    (new_amount, new_description, tx_id),
                )
                st.success("Transaction updated.")
                st.rerun()
        with col2:
            if st.button("Delete selected transaction"):
                execute("DELETE FROM finance_transaction WHERE transaction_id = %s", (tx_id,))
                st.success("Transaction deleted.")
                st.rerun()


def budgets_screen():
    user = current_user()
    st.header("Monthly Budgets CRUD")

    categories = category_options("expense")
    with st.expander("Create or update budget", expanded=True):
        with st.form("upsert_budget"):
            selected_user_id = int(user["user_id"])
            if is_admin():
                users = user_options()
                selected_user_id = users[st.selectbox("Budget owner", list(users.keys()))]
            category_id = categories[st.selectbox("Expense category", list(categories.keys()))]
            budget_month = st.date_input("Budget month", value=date.today().replace(day=1))
            amount = st.number_input("Budget amount", min_value=0.0, value=500.0, step=50.0)
            submitted = st.form_submit_button("Save budget")
        if submitted:
            execute(
                """
                INSERT INTO monthly_budget (user_id, category_id, budget_month, budget_amount)
                VALUES (%s, %s, date_trunc('month', %s::date)::date, %s)
                ON CONFLICT (user_id, category_id, budget_month)
                DO UPDATE SET budget_amount = EXCLUDED.budget_amount
                """,
                (selected_user_id, category_id, budget_month, amount),
            )
            st.success("Budget saved.")
            st.rerun()

    if is_admin():
        rows = fetch_all(
            """
            SELECT b.budget_id, u.full_name, c.category_name, b.budget_month, b.budget_amount
            FROM monthly_budget b
            JOIN app_user u ON u.user_id = b.user_id
            JOIN category c ON c.category_id = b.category_id
            ORDER BY b.budget_month DESC, u.full_name, c.category_name
            LIMIT 200
            """
        )
    else:
        rows = fetch_all(
            """
            SELECT b.budget_id, c.category_name, b.budget_month, b.budget_amount
            FROM monthly_budget b
            JOIN category c ON c.category_id = b.category_id
            WHERE b.user_id = %s
            ORDER BY b.budget_month DESC, c.category_name
            LIMIT 200
            """,
            (user["user_id"],),
        )
    st.subheader("Read budgets")
    show_table(rows)

    if rows:
        budget_map = {f'{r["budget_id"]} - {r["category_name"]} - {r["budget_month"]}': int(r["budget_id"]) for r in rows}
        budget_id = budget_map[st.selectbox("Select budget to delete", list(budget_map.keys()))]
        if st.button("Delete selected budget"):
            execute("DELETE FROM monthly_budget WHERE budget_id = %s", (budget_id,))
            st.success("Budget deleted.")
            st.rerun()


def reports_screen():
    st.header("Advanced Queries and Reports")
    report_user_id = user_selector_for_reports()

    report_name = st.selectbox(
        "Select advanced query",
        [
            "1. Monthly budget vs actual variance by category",
            "2. Six-month rolling average spending by category",
            "3. Recurring expense detection",
            "4. Savings-goal feasibility under selected forecast run",
            "5. Risky forecast month detection",
        ],
    )

    if report_name.startswith("1"):
        rows = fetch_all(
            """
            WITH actual AS (
                SELECT date_trunc('month', t.transaction_date)::date AS budget_month,
                       t.category_id,
                       SUM(t.amount_total) AS actual_spending
                FROM finance_transaction t
                WHERE t.user_id = %s AND t.transaction_type = 'expense'
                GROUP BY 1, 2
            )
            SELECT b.budget_month,
                   c.category_name,
                   b.budget_amount,
                   COALESCE(a.actual_spending, 0) AS actual_spending,
                   COALESCE(a.actual_spending, 0) - b.budget_amount AS variance_amount,
                   CASE
                       WHEN COALESCE(a.actual_spending, 0) > b.budget_amount THEN 'Over budget'
                       ELSE 'Within budget'
                   END AS budget_status
            FROM monthly_budget b
            JOIN category c ON c.category_id = b.category_id
            LEFT JOIN actual a
              ON a.budget_month = b.budget_month
             AND a.category_id = b.category_id
            WHERE b.user_id = %s
            ORDER BY b.budget_month DESC, c.category_name
            LIMIT 120
            """,
            (report_user_id, report_user_id),
        )
        st.write("Compares planned budgets with real expense transactions.")
        show_table(rows)

    elif report_name.startswith("2"):
        rows = fetch_all(
            """
            WITH monthly AS (
                SELECT date_trunc('month', t.transaction_date)::date AS spending_month,
                       t.category_id,
                       c.category_name,
                       SUM(t.amount_total) AS monthly_spending
                FROM finance_transaction t
                JOIN category c ON c.category_id = t.category_id
                WHERE t.user_id = %s AND t.transaction_type = 'expense'
                GROUP BY 1, 2, 3
            )
            SELECT spending_month,
                   category_name,
                   monthly_spending,
                   ROUND(
                       AVG(monthly_spending) OVER (
                           PARTITION BY category_id
                           ORDER BY spending_month
                           ROWS BETWEEN 5 PRECEDING AND CURRENT ROW
                       ), 2
                   ) AS six_month_rolling_average
            FROM monthly
            ORDER BY spending_month DESC, category_name
            LIMIT 150
            """,
            (report_user_id,),
        )
        st.write("Uses a window function to show category spending trends.")
        show_table(rows)

    elif report_name.startswith("3"):
        rows = fetch_all(
            """
            SELECT m.merchant_name,
                   c.category_name,
                   ROUND(t.amount_total, 0) AS approximate_amount,
                   COUNT(*) AS transaction_count,
                   COUNT(DISTINCT date_trunc('month', t.transaction_date)) AS months_seen,
                   MIN(t.transaction_date) AS first_seen,
                   MAX(t.transaction_date) AS last_seen
            FROM finance_transaction t
            JOIN merchant m ON m.merchant_id = t.merchant_id
            JOIN category c ON c.category_id = t.category_id
            WHERE t.user_id = %s AND t.transaction_type = 'expense'
            GROUP BY m.merchant_name, c.category_name, ROUND(t.amount_total, 0)
            HAVING COUNT(*) >= 3
               AND COUNT(DISTINCT date_trunc('month', t.transaction_date)) >= 3
            ORDER BY months_seen DESC, transaction_count DESC
            LIMIT 50
            """,
            (report_user_id,),
        )
        st.write("Finds merchants and approximate amounts that repeat over several months.")
        show_table(rows)

    elif report_name.startswith("4"):
        run_rows = fetch_all(
            """
            SELECT r.run_id, s.scenario_name, r.run_timestamp
            FROM forecast_run r
            JOIN forecast_scenario s ON s.scenario_id = r.scenario_id
            WHERE s.user_id = %s
            ORDER BY r.run_id DESC
            """,
            (report_user_id,),
        )
        if not run_rows:
            st.info("No forecast runs exist for this user.")
            return
        run_options = {f'{r["run_id"]} - {r["scenario_name"]}': int(r["run_id"]) for r in run_rows}
        run_id = run_options[st.selectbox("Forecast run", list(run_options.keys()))]
        rows = fetch_all(
            """
            SELECT g.goal_name,
                   a.account_name,
                   g.target_amount,
                   g.current_saved_amount,
                   g.target_date,
                   fp.result_month AS forecast_month_used,
                   fp.projected_ending_balance,
                   CASE
                       WHEN fp.projected_ending_balance >= g.target_amount THEN 'Feasible'
                       ELSE 'At risk'
                   END AS feasibility_status
            FROM savings_goal g
            JOIN account a ON a.account_id = g.linked_account_id
            LEFT JOIN LATERAL (
                SELECT far.result_month, far.projected_ending_balance
                FROM forecast_account_result far
                WHERE far.run_id = %s
                  AND far.account_id = g.linked_account_id
                  AND far.result_month <= date_trunc('month', g.target_date)::date
                ORDER BY far.result_month DESC
                LIMIT 1
            ) fp ON TRUE
            WHERE g.user_id = %s
            ORDER BY g.target_date
            """,
            (run_id, report_user_id),
        )
        st.write("Checks whether projected account balances are enough to reach savings goals.")
        show_table(rows)

    else:
        run_rows = fetch_all(
            """
            SELECT r.run_id, s.scenario_name, r.run_timestamp
            FROM forecast_run r
            JOIN forecast_scenario s ON s.scenario_id = r.scenario_id
            WHERE s.user_id = %s
            ORDER BY r.run_id DESC
            """,
            (report_user_id,),
        )
        if not run_rows:
            st.info("No forecast runs exist for this user.")
            return
        run_options = {f'{r["run_id"]} - {r["scenario_name"]}': int(r["run_id"]) for r in run_rows}
        run_id = run_options[st.selectbox("Forecast run", list(run_options.keys()), key="risk_run")]
        threshold = st.number_input("Risk threshold", min_value=0.0, value=500.0, step=100.0)
        rows = fetch_all(
            """
            SELECT a.account_name,
                   far.result_month,
                   far.projected_ending_balance,
                   CASE
                       WHEN far.projected_ending_balance < %s THEN 'Risky month'
                       ELSE 'Safe'
                   END AS risk_status
            FROM forecast_account_result far
            JOIN account a ON a.account_id = far.account_id
            WHERE far.run_id = %s
              AND far.projected_ending_balance < %s
            ORDER BY far.result_month, a.account_name
            """,
            (threshold, run_id, threshold),
        )
        st.write("Shows months where a projected account balance falls below the safety threshold.")
        show_table(rows)


def admin_screen():
    if not is_admin():
        st.error("This page is only available to admin users.")
        return

    st.header("Admin Panel")
    st.subheader("User list")
    users = fetch_all("SELECT user_id, email, full_name, role, base_currency, is_active FROM app_user ORDER BY user_id")
    show_table(users)

    st.subheader("Create user")
    with st.form("create_user"):
        email = st.text_input("New email")
        full_name = st.text_input("Full name")
        role = st.selectbox("Role", ["user", "admin"])
        password = st.text_input("Temporary password", type="password")
        submitted = st.form_submit_button("Create user")
    if submitted:
        execute(
            """
            INSERT INTO app_user (email, password_hash, full_name, role, base_currency)
            VALUES (%s, %s, %s, %s, 'USD')
            """,
            (email, hash_password(password), full_name, role),
        )
        st.success("User created.")
        st.rerun()

    st.subheader("Categories")
    show_table(fetch_all("SELECT category_id, category_name, category_type FROM category ORDER BY category_type, category_name"))
    with st.form("create_category"):
        name = st.text_input("Category name")
        typ = st.selectbox("Category type", ["income", "expense", "transfer", "savings"])
        submitted_category = st.form_submit_button("Create category")
    if submitted_category:
        execute("INSERT INTO category (category_name, category_type) VALUES (%s, %s)", (name, typ))
        st.success("Category created.")
        st.rerun()


def demo_checklist_screen():
    st.header("10-Minute Live Demo Checklist")
    st.markdown(
        """
        1. Login as admin and show the dashboard.
        2. Show the standard user list in the Admin Panel.
        3. Create, update, and delete one account.
        4. Create, update, and delete one transaction.
        5. Create or update one monthly budget.
        6. Run the five advanced query reports.
        7. Logout and login as `alex@example.com` to show role-based access.
        """
    )
    st.info("For the final report, take screenshots of each screen above after running the app.")


# -----------------------------
# Main app
# -----------------------------

if "user" not in st.session_state:
    login_screen()
else:
    user = current_user()
    st.sidebar.title("Finance App")
    st.sidebar.write(f"{user['full_name']} ({user['role']})")
    if st.sidebar.button("Logout"):
        st.session_state.clear()
        st.rerun()

    pages = ["Dashboard", "Accounts CRUD", "Transactions CRUD", "Budgets CRUD", "Reports", "Demo Checklist"]
    if is_admin():
        pages.insert(5, "Admin Panel")
    page = st.sidebar.radio("Menu", pages)

    try:
        if page == "Dashboard":
            dashboard_screen()
        elif page == "Accounts CRUD":
            accounts_screen()
        elif page == "Transactions CRUD":
            transactions_screen()
        elif page == "Budgets CRUD":
            budgets_screen()
        elif page == "Reports":
            reports_screen()
        elif page == "Admin Panel":
            admin_screen()
        else:
            demo_checklist_screen()
    except Exception as exc:
        st.error("An application error occurred. Check the database setup and SQL files.")
        st.code(str(exc))
