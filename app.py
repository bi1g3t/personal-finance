from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import Any

import pandas as pd
import streamlit as st

from auth import hash_password, verify_password
from db import execute, fetch_all, fetch_one

st.set_page_config(
    page_title="Personal Finance Platform",
    layout="wide",
)


REPORT_NAMES = [
    "Budget variance by category",
    "Six-month spending trend",
    "Recurring expense detection",
    "Savings goal feasibility",
    "Balance risk detection",
]


def show_table(rows: list[dict[str, Any]], empty_message: str = "No records found.") -> None:
    if rows:
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    else:
        st.info(empty_message)


def to_money(value: Any) -> str:
    if value is None:
        value = 0
    return f"{float(value):,.2f}"


def first_day(value: date) -> date:
    return date(value.year, value.month, 1)


def add_months(value: date, months: int) -> date:
    year = value.year + (value.month - 1 + months) // 12
    month = (value.month - 1 + months) % 12 + 1
    return date(year, month, 1)


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


def current_user() -> dict[str, Any]:
    return st.session_state.get("user", {})


def is_admin() -> bool:
    user = current_user()
    return bool(user and user.get("role") == "admin")


def active_user_options(include_all: bool = False) -> dict[str, int | None]:
    rows = fetch_all(
        "SELECT user_id, full_name, email FROM app_user WHERE is_active = TRUE ORDER BY full_name"
    )
    options: dict[str, int | None] = {}
    if include_all:
        options["All users"] = None
    for row in rows:
        options[f'{row["full_name"]} ({row["email"]})'] = int(row["user_id"])
    return options


def user_selector(label: str = "User", key: str = "user_select") -> int:
    user = current_user()
    if not is_admin():
        return int(user["user_id"])
    options = active_user_options(include_all=False)
    selected = st.selectbox(label, list(options.keys()), key=key)
    return int(options[selected])


def category_options(category_type: str | None = None, include_all: bool = False) -> dict[str, int | None]:
    if category_type:
        rows = fetch_all(
            "SELECT category_id, category_name FROM category WHERE category_type = %s ORDER BY category_name",
            (category_type,),
        )
    else:
        rows = fetch_all("SELECT category_id, category_name FROM category ORDER BY category_name")
    options: dict[str, int | None] = {}
    if include_all:
        options["All categories"] = None
    for row in rows:
        options[row["category_name"]] = int(row["category_id"])
    return options


def merchant_options(include_all: bool = False) -> dict[str, int | None]:
    rows = fetch_all("SELECT merchant_id, merchant_name FROM merchant ORDER BY merchant_name")
    options: dict[str, int | None] = {}
    if include_all:
        options["All merchants"] = None
    for row in rows:
        options[row["merchant_name"]] = int(row["merchant_id"])
    return options


def account_options(user_id: int | None = None, include_all: bool = False) -> dict[str, int | None]:
    params: tuple[Any, ...] = ()
    where = ""
    if user_id is not None:
        where = "WHERE a.user_id = %s"
        params = (user_id,)
    elif not is_admin():
        where = "WHERE a.user_id = %s"
        params = (int(current_user()["user_id"]),)

    rows = fetch_all(
        f"""
        SELECT a.account_id, a.account_name, u.full_name
        FROM account a
        JOIN app_user u ON u.user_id = a.user_id
        {where}
        ORDER BY u.full_name, a.account_name
        """,
        params,
    )
    options: dict[str, int | None] = {}
    if include_all:
        options["All accounts"] = None
    for row in rows:
        label = row["account_name"] if not is_admin() else f'{row["account_name"]} - {row["full_name"]}'
        options[label] = int(row["account_id"])
    return options


def login_screen() -> None:
    st.title("Personal Finance Simulation & Forecasting Platform")
    st.write("Sign in to manage accounts, transactions, budgets, and financial reports.")

    with st.form("login_form"):
        email = st.text_input("Email")
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Sign in")

    if submitted:
        if not email or not password:
            st.warning("Enter both email and password.")
            return
        try:
            if login_user(email, password):
                st.rerun()
            else:
                st.error("Invalid email or password.")
        except Exception as exc:
            st.error("The application could not connect to the database.")
            st.code(str(exc))


def dashboard_screen() -> None:
    user = current_user()
    st.header("Dashboard")
    st.write(f"Signed in as **{user['full_name']}**. Access level: **{user['role']}**.")

    if is_admin():
        metrics = fetch_one(
            """
            SELECT
                (SELECT COUNT(*) FROM app_user WHERE is_active = TRUE) AS users,
                (SELECT COUNT(*) FROM account) AS accounts,
                (SELECT COUNT(*) FROM finance_transaction) AS transactions,
                (SELECT COALESCE(SUM(current_balance), 0) FROM account) AS total_balance
            """
        ) or {}
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
        ) or {}

    c1, c2, c3, c4 = st.columns(4)
    if is_admin():
        c1.metric("Active users", metrics.get("users", 0))
        c2.metric("Accounts", metrics.get("accounts", 0))
        c3.metric("Transactions", metrics.get("transactions", 0))
        c4.metric("Total balance", to_money(metrics.get("total_balance", 0)))
    else:
        c1.metric("Accounts", metrics.get("accounts", 0))
        c2.metric("Transactions", metrics.get("transactions", 0))
        c3.metric("Total balance", to_money(metrics.get("total_balance", 0)))
        c4.metric("This month spending", to_money(metrics.get("this_month_spending", 0)))

    st.subheader("Recent transactions")
    if is_admin():
        rows = fetch_all(
            """
            SELECT t.transaction_id, u.full_name, a.account_name, c.category_name,
                   m.merchant_name, t.transaction_date, t.transaction_type,
                   t.amount_total, t.description
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
                   m.merchant_name, t.transaction_date, t.transaction_type,
                   t.amount_total, t.description
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


def accounts_screen() -> None:
    user = current_user()
    st.header("Accounts")
    st.write("Create, view, edit, and delete financial accounts.")

    institutions = fetch_all(
        "SELECT institution_id, institution_name FROM financial_institution ORDER BY institution_name"
    )
    institution_map = {row["institution_name"]: int(row["institution_id"]) for row in institutions}

    with st.expander("Add account", expanded=True):
        with st.form("create_account"):
            selected_user_id = int(user["user_id"])
            if is_admin():
                users = active_user_options(include_all=False)
                selected_user_id = int(users[st.selectbox("Owner", list(users.keys()))])
            institution_id = None
            if institution_map:
                institution_id = institution_map[st.selectbox("Institution", list(institution_map.keys()))]
            account_name = st.text_input("Account name")
            account_type = st.selectbox("Account type", ["checking", "savings", "credit", "investment"])
            balance = st.number_input("Current balance", min_value=-100000.0, max_value=1000000.0, value=0.0, step=100.0)
            currency = st.text_input("Currency", value="USD", max_chars=3)
            submitted = st.form_submit_button("Add account")

        if submitted:
            if not account_name.strip():
                st.warning("Account name is required.")
            else:
                execute(
                    """
                    INSERT INTO account (user_id, institution_id, account_name, account_type, current_balance, currency_code)
                    VALUES (%s, %s, %s, %s, %s, upper(%s))
                    """,
                    (selected_user_id, institution_id, account_name.strip(), account_type, balance, currency),
                )
                st.success("Account added.")
                st.rerun()

    st.subheader("Account list")
    selected_user_filter: int | None = None
    if is_admin():
        user_filter_map = active_user_options(include_all=True)
        selected_user_filter = user_filter_map[st.selectbox("Owner filter", list(user_filter_map.keys()), key="account_owner_filter")]

    where = ""
    params: tuple[Any, ...] = ()
    if selected_user_filter is not None:
        where = "WHERE a.user_id = %s"
        params = (selected_user_filter,)
    elif not is_admin():
        where = "WHERE a.user_id = %s"
        params = (int(user["user_id"]),)

    rows = fetch_all(
        f"""
        SELECT a.account_id, u.full_name, a.account_name, a.account_type,
               a.current_balance, a.currency_code, fi.institution_name
        FROM account a
        JOIN app_user u ON u.user_id = a.user_id
        LEFT JOIN financial_institution fi ON fi.institution_id = a.institution_id
        {where}
        ORDER BY u.full_name, a.account_name
        """,
        params,
    )
    show_table(rows)

    account_map = account_options(selected_user_filter, include_all=False)
    if account_map:
        st.subheader("Edit or delete account")
        selected_account_id = int(account_map[st.selectbox("Account", list(account_map.keys()), key="account_update_select")])
        existing = fetch_one("SELECT * FROM account WHERE account_id = %s", (selected_account_id,))
        if existing:
            col1, col2 = st.columns(2)
            with col1:
                with st.form("update_account"):
                    new_name = st.text_input("Account name", value=existing["account_name"])
                    account_types = ["checking", "savings", "credit", "investment"]
                    new_type = st.selectbox(
                        "Account type",
                        account_types,
                        index=account_types.index(existing["account_type"]),
                    )
                    new_balance = st.number_input("Current balance", value=float(existing["current_balance"]), step=100.0)
                    update_clicked = st.form_submit_button("Save changes")
                if update_clicked:
                    execute(
                        "UPDATE account SET account_name = %s, account_type = %s, current_balance = %s WHERE account_id = %s",
                        (new_name.strip(), new_type, new_balance, selected_account_id),
                    )
                    st.success("Account updated.")
                    st.rerun()
            with col2:
                st.warning("Deleting an account also removes related transactions because of database relationships.")
                if st.button("Delete account"):
                    execute("DELETE FROM account WHERE account_id = %s", (selected_account_id,))
                    st.success("Account deleted.")
                    st.rerun()


def transaction_filters() -> tuple[str, list[Any], int, int | None]:
    user = current_user()
    st.subheader("Transaction search")
    c1, c2, c3 = st.columns(3)

    selected_user_id: int | None = int(user["user_id"])
    with c1:
        if is_admin():
            user_map = active_user_options(include_all=True)
            selected_user_id = user_map[st.selectbox("User", list(user_map.keys()), key="tx_user_filter")]
        else:
            st.text_input("User", value=user["full_name"], disabled=True)

    with c2:
        range_choice = st.selectbox(
            "Date range",
            ["All dates", "This month", "Last 3 months", "Last 6 months", "Custom"],
            index=0,
        )
    today = date.today()
    start_date: date | None = None
    end_date: date | None = None
    if range_choice == "This month":
        start_date = first_day(today)
        end_date = today
    elif range_choice == "Last 3 months":
        start_date = add_months(first_day(today), -2)
        end_date = today
    elif range_choice == "Last 6 months":
        start_date = add_months(first_day(today), -5)
        end_date = today
    elif range_choice == "Custom":
        with c3:
            custom_dates = st.date_input("Start and end date", value=(add_months(today, -1), today))
        if isinstance(custom_dates, tuple) and len(custom_dates) == 2:
            start_date, end_date = custom_dates
    else:
        with c3:
            st.write("All available transaction dates are included.")

    c4, c5, c6 = st.columns(3)
    with c4:
        account_map = account_options(selected_user_id, include_all=True)
        account_id = account_map[st.selectbox("Account", list(account_map.keys()), key="tx_account_filter")]
    with c5:
        cat_map = category_options(include_all=True)
        category_id = cat_map[st.selectbox("Category", list(cat_map.keys()), key="tx_category_filter")]
    with c6:
        type_choice = st.selectbox("Transaction type", ["All types", "expense", "income", "transfer"], key="tx_type_filter")

    c7, c8, c9 = st.columns(3)
    with c7:
        mer_map = merchant_options(include_all=True)
        merchant_id = mer_map[st.selectbox("Merchant", list(mer_map.keys()), key="tx_merchant_filter")]
    with c8:
        keyword = st.text_input("Description contains", key="tx_keyword_filter")
    with c9:
        row_limit = int(st.selectbox("Maximum rows to display", [50, 100, 250, 500, 1000, 2500, 5000], index=3))

    where_parts: list[str] = []
    params: list[Any] = []
    if selected_user_id is not None:
        where_parts.append("t.user_id = %s")
        params.append(selected_user_id)
    elif not is_admin():
        where_parts.append("t.user_id = %s")
        params.append(int(user["user_id"]))
    if start_date is not None:
        where_parts.append("t.transaction_date >= %s")
        params.append(start_date)
    if end_date is not None:
        where_parts.append("t.transaction_date <= %s")
        params.append(end_date)
    if account_id is not None:
        where_parts.append("t.account_id = %s")
        params.append(account_id)
    if category_id is not None:
        where_parts.append("t.category_id = %s")
        params.append(category_id)
    if merchant_id is not None:
        where_parts.append("t.merchant_id = %s")
        params.append(merchant_id)
    if type_choice != "All types":
        where_parts.append("t.transaction_type = %s")
        params.append(type_choice)
    if keyword.strip():
        where_parts.append("COALESCE(t.description, '') ILIKE %s")
        params.append(f"%{keyword.strip()}%")

    where_sql = "WHERE " + " AND ".join(where_parts) if where_parts else ""
    return where_sql, params, row_limit, selected_user_id


def transactions_screen() -> None:
    user = current_user()
    st.header("Transactions")
    st.write("Add transactions and search existing records by user, month, account, category, merchant, and type.")

    accounts = account_options(None, include_all=False)
    categories = category_options(include_all=False)
    merchants = merchant_options(include_all=False)

    if not accounts:
        st.warning("Create at least one account before adding transactions.")
        return

    with st.expander("Add transaction", expanded=True):
        with st.form("create_transaction"):
            account_id = int(accounts[st.selectbox("Account", list(accounts.keys()), key="create_tx_account")])
            category_id = int(categories[st.selectbox("Category", list(categories.keys()), key="create_tx_category")])
            merchant_id = int(merchants[st.selectbox("Merchant", list(merchants.keys()), key="create_tx_merchant")])
            transaction_date = st.date_input("Transaction date", value=date.today(), key="create_tx_date")
            transaction_type = st.selectbox("Transaction type", ["expense", "income", "transfer"], key="create_tx_type")
            amount = st.number_input("Amount", min_value=0.01, max_value=100000.0, value=50.0, step=10.0)
            description = st.text_input("Description", value="Manual entry")
            submitted = st.form_submit_button("Add transaction")
        if submitted:
            owner = fetch_one("SELECT user_id FROM account WHERE account_id = %s", (account_id,))
            if not owner:
                st.error("Selected account was not found.")
            else:
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
                        (owner_id, account_id, merchant_id, category_id, transaction_date, transaction_type, amount, description.strip()),
                    )
                    st.success("Transaction added.")
                    st.rerun()

    where_sql, params, row_limit, _ = transaction_filters()

    count_row = fetch_one(
        f"""
        SELECT COUNT(*) AS matching_rows
        FROM finance_transaction t
        JOIN account a ON a.account_id = t.account_id
        LEFT JOIN category c ON c.category_id = t.category_id
        LEFT JOIN merchant m ON m.merchant_id = t.merchant_id
        {where_sql}
        """,
        tuple(params),
    ) or {"matching_rows": 0}

    rows = fetch_all(
        f"""
        SELECT t.transaction_id, u.full_name, a.account_name, c.category_name,
               m.merchant_name, t.transaction_date, t.transaction_type,
               t.amount_total, t.description
        FROM finance_transaction t
        JOIN app_user u ON u.user_id = t.user_id
        JOIN account a ON a.account_id = t.account_id
        LEFT JOIN category c ON c.category_id = t.category_id
        LEFT JOIN merchant m ON m.merchant_id = t.merchant_id
        {where_sql}
        ORDER BY t.transaction_date DESC, t.transaction_id DESC
        LIMIT %s
        """,
        tuple(params + [row_limit]),
    )

    st.subheader("Transaction list")
    st.write(f"Showing {len(rows)} of {count_row['matching_rows']} matching transactions.")
    show_table(rows)

    if rows:
        csv_data = pd.DataFrame(rows).to_csv(index=False).encode("utf-8")
        st.download_button("Download displayed rows as CSV", csv_data, "transactions.csv", "text/csv")

        st.subheader("Edit or delete transaction")
        tx_map = {
            f'{r["transaction_id"]} - {r.get("transaction_date")} - {r.get("merchant_name") or "No merchant"} - {r.get("amount_total")}': int(r["transaction_id"])
            for r in rows
        }
        tx_id = int(tx_map[st.selectbox("Transaction", list(tx_map.keys()), key="tx_update_select")])
        existing = fetch_one("SELECT * FROM finance_transaction WHERE transaction_id = %s", (tx_id,))
        if existing:
            col1, col2 = st.columns(2)
            with col1:
                with st.form("update_transaction"):
                    new_date = st.date_input("Transaction date", value=existing["transaction_date"])
                    new_type = st.selectbox(
                        "Transaction type",
                        ["expense", "income", "transfer"],
                        index=["expense", "income", "transfer"].index(existing["transaction_type"]),
                    )
                    new_amount = st.number_input("Amount", min_value=0.01, value=float(existing["amount_total"]), step=10.0)
                    new_description = st.text_input("Description", value=existing.get("description") or "")
                    update_clicked = st.form_submit_button("Save changes")
                if update_clicked:
                    execute(
                        """
                        UPDATE finance_transaction
                        SET transaction_date = %s, transaction_type = %s, amount_total = %s, description = %s
                        WHERE transaction_id = %s
                        """,
                        (new_date, new_type, new_amount, new_description.strip(), tx_id),
                    )
                    st.success("Transaction updated.")
                    st.rerun()
            with col2:
                if st.button("Delete transaction"):
                    execute("DELETE FROM finance_transaction WHERE transaction_id = %s", (tx_id,))
                    st.success("Transaction deleted.")
                    st.rerun()


def budgets_screen() -> None:
    user = current_user()
    st.header("Monthly budgets")
    st.write("Set planned spending amounts and compare them with actual expenses in the reports.")

    categories = category_options("expense")
    if not categories:
        st.warning("No expense categories are available.")
        return

    with st.expander("Add or update budget", expanded=True):
        with st.form("upsert_budget"):
            selected_user_id = int(user["user_id"])
            if is_admin():
                users = active_user_options(include_all=False)
                selected_user_id = int(users[st.selectbox("Budget owner", list(users.keys()))])
            category_id = int(categories[st.selectbox("Expense category", list(categories.keys()))])
            budget_month = st.date_input("Budget month", value=first_day(date.today()))
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

    st.subheader("Budget list")
    c1, c2, c3 = st.columns(3)
    selected_user_id: int | None = int(user["user_id"])
    with c1:
        if is_admin():
            users = active_user_options(include_all=True)
            selected_user_id = users[st.selectbox("Owner", list(users.keys()), key="budget_user_filter")]
    with c2:
        category_filter_map = category_options("expense", include_all=True)
        selected_category_id = category_filter_map[st.selectbox("Category", list(category_filter_map.keys()), key="budget_category_filter")]
    with c3:
        budget_limit = int(st.selectbox("Maximum rows", [50, 100, 250, 500], index=1, key="budget_limit"))

    where_parts: list[str] = []
    params: list[Any] = []
    if selected_user_id is not None:
        where_parts.append("b.user_id = %s")
        params.append(selected_user_id)
    if selected_category_id is not None:
        where_parts.append("b.category_id = %s")
        params.append(selected_category_id)
    where_sql = "WHERE " + " AND ".join(where_parts) if where_parts else ""

    rows = fetch_all(
        f"""
        SELECT b.budget_id, u.full_name, c.category_name, b.budget_month, b.budget_amount
        FROM monthly_budget b
        JOIN app_user u ON u.user_id = b.user_id
        JOIN category c ON c.category_id = b.category_id
        {where_sql}
        ORDER BY b.budget_month DESC, u.full_name, c.category_name
        LIMIT %s
        """,
        tuple(params + [budget_limit]),
    )
    show_table(rows)

    if rows:
        budget_map = {f'{r["budget_id"]} - {r["category_name"]} - {r["budget_month"]}': int(r["budget_id"]) for r in rows}
        budget_id = int(budget_map[st.selectbox("Budget to delete", list(budget_map.keys()))])
        if st.button("Delete budget"):
            execute("DELETE FROM monthly_budget WHERE budget_id = %s", (budget_id,))
            st.success("Budget deleted.")
            st.rerun()


def reports_screen() -> None:
    st.header("Reports and analytics")
    report_user_id = user_selector("Report owner", key="report_owner_select")

    report_name = st.selectbox("Report type", REPORT_NAMES)

    if report_name == "Budget variance by category":
        with st.expander("How this report is calculated", expanded=False):
            st.write(
                "The query groups expense transactions by month and category, joins the result to monthly budgets, "
                "and calculates actual spending minus budget amount. A positive variance means spending is over budget."
            )
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
            LIMIT 250
            """,
            (report_user_id, report_user_id),
        )
        show_table(rows)

    elif report_name == "Six-month spending trend":
        with st.expander("How this report is calculated", expanded=False):
            st.write(
                "The query first calculates total spending for each category in each month. It then uses a SQL window function "
                "to calculate the average of the current month and previous five monthly totals. This is historical trend analysis, "
                "not a machine learning forecast and not a simple multiplication formula."
            )
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
            LIMIT 250
            """,
            (report_user_id,),
        )
        show_table(rows)

    elif report_name == "Recurring expense detection":
        c1, c2 = st.columns(2)
        with c1:
            min_count = int(st.number_input("Minimum repeated transactions", min_value=2, max_value=12, value=3, step=1))
        with c2:
            min_months = int(st.number_input("Minimum months seen", min_value=2, max_value=12, value=3, step=1))
        with st.expander("How this report is calculated", expanded=False):
            st.write(
                "The query groups expenses by merchant, category, and rounded amount. A group is marked as recurring only if it "
                "appears at least the selected number of times and across at least the selected number of distinct months."
            )
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
            HAVING COUNT(*) >= %s
               AND COUNT(DISTINCT date_trunc('month', t.transaction_date)) >= %s
            ORDER BY months_seen DESC, transaction_count DESC, merchant_name
            LIMIT 100
            """,
            (report_user_id, min_count, min_months),
        )
        show_table(rows)

    elif report_name == "Savings goal feasibility":
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
        run_id = int(run_options[st.selectbox("Forecast result set", list(run_options.keys()))])
        with st.expander("How this report is calculated", expanded=False):
            st.write(
                "The query checks each savings goal against the selected stored forecast result set. For each goal, it finds the "
                "latest projected balance before the goal target date and compares that balance with the target amount."
            )
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
                       WHEN fp.projected_ending_balance IS NULL THEN 'No forecast value'
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
        run_id = int(run_options[st.selectbox("Forecast result set", list(run_options.keys()), key="risk_run")])
        c1, c2 = st.columns(2)
        with c1:
            threshold = st.number_input("Safety threshold amount", min_value=0.0, value=500.0, step=100.0)
        with c2:
            show_only_risky = st.checkbox("Show only rows below threshold", value=True)
        with st.expander("How this report is calculated", expanded=False):
            st.write(
                "The query compares every projected account ending balance with the selected safety threshold. If the projected "
                "balance is lower than the threshold, the month is marked as risky. Changing the threshold changes the risk status."
            )
        filter_sql = "AND far.projected_ending_balance < %s" if show_only_risky else ""
        params: list[Any] = [threshold, run_id]
        if show_only_risky:
            params.append(threshold)
        rows = fetch_all(
            f"""
            SELECT a.account_name,
                   far.result_month,
                   far.projected_ending_balance,
                   %s::numeric AS safety_threshold,
                   CASE
                       WHEN far.projected_ending_balance < %s THEN 'Risky'
                       ELSE 'Safe'
                   END AS risk_status
            FROM forecast_account_result far
            JOIN account a ON a.account_id = far.account_id
            WHERE far.run_id = %s
              {filter_sql}
            ORDER BY far.result_month, a.account_name
            LIMIT 300
            """,
            tuple([threshold, threshold, run_id] + ([threshold] if show_only_risky else [])),
        )
        show_table(rows)


def admin_screen() -> None:
    if not is_admin():
        st.error("This page is only available to administrator users.")
        return

    st.header("User and category management")

    st.subheader("Users")
    users = fetch_all(
        "SELECT user_id, email, full_name, role, base_currency, is_active FROM app_user ORDER BY user_id"
    )
    show_table(users)

    with st.expander("Add user"):
        with st.form("create_user"):
            email = st.text_input("Email")
            full_name = st.text_input("Full name")
            role = st.selectbox("Role", ["user", "admin"])
            password = st.text_input("Temporary password", type="password")
            submitted = st.form_submit_button("Add user")
        if submitted:
            if not email.strip() or not full_name.strip() or not password:
                st.warning("Email, name, and password are required.")
            else:
                execute(
                    """
                    INSERT INTO app_user (email, password_hash, full_name, role, base_currency)
                    VALUES (%s, %s, %s, %s, 'USD')
                    """,
                    (email.strip(), hash_password(password), full_name.strip(), role),
                )
                st.success("User added.")
                st.rerun()

    st.subheader("Categories")
    show_table(fetch_all("SELECT category_id, category_name, category_type FROM category ORDER BY category_type, category_name"))
    with st.expander("Add category"):
        with st.form("create_category"):
            name = st.text_input("Category name")
            typ = st.selectbox("Category type", ["income", "expense", "transfer", "savings"])
            submitted_category = st.form_submit_button("Add category")
        if submitted_category:
            if not name.strip():
                st.warning("Category name is required.")
            else:
                execute("INSERT INTO category (category_name, category_type) VALUES (%s, %s)", (name.strip(), typ))
                st.success("Category added.")
                st.rerun()


if "user" not in st.session_state:
    login_screen()
else:
    user = current_user()
    st.sidebar.title("Finance App")
    st.sidebar.write(f"{user['full_name']} ({user['role']})")
    if st.sidebar.button("Sign out"):
        st.session_state.clear()
        st.rerun()

    pages = ["Dashboard", "Accounts", "Transactions", "Monthly budgets", "Reports and analytics"]
    if is_admin():
        pages.append("User and category management")
    page = st.sidebar.radio("Navigation", pages)

    try:
        if page == "Dashboard":
            dashboard_screen()
        elif page == "Accounts":
            accounts_screen()
        elif page == "Transactions":
            transactions_screen()
        elif page == "Monthly budgets":
            budgets_screen()
        elif page == "Reports and analytics":
            reports_screen()
        else:
            admin_screen()
    except Exception as exc:
        st.error("An application error occurred.")
        st.code(str(exc))
