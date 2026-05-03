# Personal Finance Simulation and Forecasting Platform

A Streamlit application backed by PostgreSQL for managing personal finance data and producing financial reports.

## Main features

- User login with administrator and standard user roles
- Account management
- Transaction management with filters by user, date range, account, category, merchant, and transaction type
- Monthly budget management
- Administrator user and category management
- Reports for budget variance, spending trends, recurring expenses, savings goal feasibility, and balance risk detection

## Required environment

- Python 3.10 or newer
- PostgreSQL database
- Streamlit

Install dependencies with:

```bash
pip install -r requirements.txt
```

## Database setup

Load the database dump into PostgreSQL:

```bash
psql -d YOUR_DATABASE_NAME -f sql/final_database_dump.sql
```

For Supabase, paste the SQL file content into the Supabase SQL Editor and run it.

## Database connection

Create a local file named `.streamlit/secrets.toml` using this format:

```toml
[database]
url = "postgresql://USERNAME:PASSWORD@HOST:PORT/DATABASE?sslmode=require"
```

Do not upload `.streamlit/secrets.toml` to GitHub because it contains the database password.

## Run the application

```bash
streamlit run app.py
```

Sample accounts included with the seed data:

- Administrator: `admin@example.com` / `admin123`
- Standard user: `alex@example.com` / `user123`
