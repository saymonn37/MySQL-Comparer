# MySQL Comparer

## 📌 Overview

**Database Comparer** is a GUI-based Python application that allows users to track and compare changes in a MySQL database. It captures the state of all tables at a given point in time, compares them to the latest database state, and highlights differences in data. The tool also provides the ability to export comparison results to a CSV file for further analysis.

## 🎯 Features

- ✅ **Capture Initial Database State** – Fetches and stores the state of all tables in the connected database.
- ✅ **Compare Database Changes** – Identifies added, removed, and modified records and fields.
- ✅ **User-Friendly Interface** – Built with `Tkinter`, providing an intuitive experience.
- ✅ **CSV Export** – Exports differences into a `.csv` file for documentation or further analysis.
- ✅ **Multi-threading Support** – Prevents UI freezing by executing database operations in separate threads.
- ✅ **Configurable Database Connection** – Uses `config.ini` to manage MySQL connection details.

## 🛠️ Requirements

Before running the script, ensure you have the following installed:

- Python 3.x
- `mysql-connector-python`
- `tkinter` (built-in with Python)
- `configparser`

Install missing dependencies using:

```bash
pip install mysql-connector-python
```

## 📥 Installation

1. Clone the repository:

   ```bash
   git clone https://github.com/saymonn37/MySQL-Comparer.git
   cd MySQL-Comparer
   ```

2. Create a `config.ini` file in the root directory with the following structure:

   ```ini
   [mysql]
   host = your_mysql_host
   user = your_mysql_user
   password = your_mysql_password
   database = your_database_name
   ```

3. Run the script:

   ```bash
   python3 database_comparer.py
   ```

## 🚀 Usage

1. **Fetch State** – Click the **"Fetch State"** button to capture the initial database state.
2. **Modify Database Data** – Make changes to the database through SQL or an external application.
3. **Compare States** – Click **"Compare States"** to analyze differences.
4. **Export to CSV** – Save comparison results by clicking **"Export to CSV"**.
5. **Clear All** – Reset the state tracking.

## 🖥️ GUI Overview

The application consists of:

- **Control Panel**: Buttons for fetching state, comparing changes, exporting results, and clearing data.
- **Comparison Table**: Displays detected changes with the following columns:
  - **Table Name** – The affected database table.
  - **ID** – The primary key or first column value.
  - **Column** – The column number.
  - **Column Name** – Name of the modified column.
  - **Old Value** – Previous value before modification.
  - **New Value** – Updated value.

## 📜 Example Output

If a row is modified in a table:

| Table  | ID | Column | Column Name | Old Value | New Value |
|--------|----|--------|-------------|-----------|-----------|
| users  | 1  | 2      | username    | JohnDoe   | John_Doe  |
| orders | 5  | 4      | status      | pending   | shipped   |

## 🛑 Error Handling

- If MySQL credentials are incorrect, an error message will be displayed.
- If no database state is captured before comparison, an alert is shown.
- If an error occurs during CSV export, the user will be notified.

## 🏗️ Future Improvements

- Add support for other database types (PostgreSQL, SQLite).
- Enhance UI for a better user experience.
- Implement logging for troubleshooting.

## 🔧 Troubleshooting

| Issue | Solution |
|------|---------|
| GUI not opening | Ensure Tkinter is installed. Run `python3 -m tkinter` to check. |
| Database connection error | Verify credentials in `config.ini`. |
| No changes detected | Ensure modifications were made to the database. |

## 📝 License

This project is open-source under the **MIT License**.

## 👥 Author

Developed by [Saymonn](https://github.com/saymonn37). Contributions and feedback are welcome!
