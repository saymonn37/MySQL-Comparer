#!/usr/bin/python3

import mysql.connector
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import csv
import configparser
import os
import threading

class DBManager:
    def __init__(self):
        self.script_directory = os.path.dirname(os.path.abspath(__file__))
        self.config = self.load_config()
        self.column_cache = {}
    def load_config(self):
        config = configparser.ConfigParser()
        config.read(os.path.join(self.script_directory, 'config.ini'))
        return {'host': config['mysql']['host'], 'user': config['mysql']['user'], 'password': config['mysql']['password'], 'database': config['mysql']['database']}
    def connect(self):
        return mysql.connector.connect(**self.config)
    def get_tables(self):
        conn = self.connect()
        cursor = conn.cursor()
        cursor.execute("SHOW TABLES")
        tables = [t[0] for t in cursor.fetchall()]
        cursor.close()
        conn.close()
        return tables
    def get_table_columns(self, table):
        if table in self.column_cache:
            return self.column_cache[table]
        conn = self.connect()
        cursor = conn.cursor()
        cursor.execute(f"SHOW COLUMNS FROM {table}")
        columns = [col[0] for col in cursor.fetchall()]
        cursor.close()
        conn.close()
        self.column_cache[table] = columns
        return columns
    def fetch_table_state(self, table):
        conn = self.connect()
        cursor = conn.cursor()
        cursor.execute(f"SELECT * FROM {table}")
        rows = cursor.fetchall()
        columns = self.get_table_columns(table)
        cursor.close()
        conn.close()
        state = {}
        for row in rows:
            key = row[0]
            state[key] = row
        return state

class DatabaseComparer:
    def __init__(self, root):
        self.root = root
        self.root.title("Database Comparer")
        self.db_manager = DBManager()
        self.initial_state = {}
        self.current_state = {}
        self.create_widgets()
    def create_widgets(self):
        self.button_frame = ttk.Frame(self.root)
        self.button_frame.pack(pady=10)
        self.fetch_state_button = ttk.Button(self.button_frame, text="Fetch State", command=self.thread_fetch_state)
        self.fetch_state_button.pack(side="left", padx=10)
        self.compare_states_button = ttk.Button(self.button_frame, text="Compare States", command=self.thread_compare_states)
        self.compare_states_button.pack(side="left", padx=10)
        self.export_csv_button = ttk.Button(self.button_frame, text="Export to CSV", command=self.export_to_csv)
        self.export_csv_button.pack(side="left", padx=10)
        self.clear_all_button = ttk.Button(self.button_frame, text="Clear All", command=self.clear_all)
        self.clear_all_button.pack(side="left", padx=10)
        self.result_frame = ttk.Frame(self.root)
        self.result_frame.pack(padx=10, pady=10, fill="both", expand=True)
        self.columns = ("table", "id", "column", "column_name", "old_value", "new_value")
        self.result_table = ttk.Treeview(self.result_frame, columns=self.columns, show="headings")
        self.result_table.heading("table", text="Table")
        self.result_table.heading("id", text="ID (First Column Value)")
        self.result_table.heading("column", text="Column Number")
        self.result_table.heading("column_name", text="Column Name")
        self.result_table.heading("old_value", text="Old Value")
        self.result_table.heading("new_value", text="New Value")
        self.result_table.column("table", width=100)
        self.result_table.column("id", width=150)
        self.result_table.column("column", width=100)
        self.result_table.column("column_name", width=150)
        self.result_table.column("old_value", width=200)
        self.result_table.column("new_value", width=200)
        self.result_table.pack(side="left", fill="both", expand=True)
        self.scrollbar = ttk.Scrollbar(self.result_frame, orient="vertical", command=self.result_table.yview)
        self.scrollbar.pack(side="left", fill="y")
        self.result_table.config(yscrollcommand=self.scrollbar.set)
        self.result_table.bind("<Double-1>", self.show_full_value)
        self.root.minsize(800, 400)
    def thread_fetch_state(self):
        threading.Thread(target=self.fetch_state).start()
    def fetch_state(self):
        try:
            tables = self.db_manager.get_tables()
            new_state = {}
            for table in tables:
                new_state[table] = self.db_manager.fetch_table_state(table)
            self.initial_state = new_state
            self.root.after(0, lambda: messagebox.showinfo("Database Comparer", "Database state fetched successfully."))
        except Exception as e:
            self.root.after(0, lambda: messagebox.showerror("Database Comparer", f"Error fetching state:\n{str(e)}"))
    def thread_compare_states(self):
        threading.Thread(target=self.compare_states).start()
    def compare_states(self):
        if not self.initial_state:
            self.root.after(0, lambda: messagebox.showerror("Database Comparer", "Initial state not fetched. Use Fetch State button."))
            return
        try:
            tables = self.db_manager.get_tables()
            new_state = {}
            for table in tables:
                new_state[table] = self.db_manager.fetch_table_state(table)
            self.current_state = new_state
            differences = []
            all_tables = set(list(self.initial_state.keys()) + list(self.current_state.keys()))
            for table in all_tables:
                columns = self.db_manager.get_table_columns(table)
                initial_table = self.initial_state.get(table, {})
                current_table = self.current_state.get(table, {})
                all_keys = set(list(initial_table.keys()) + list(current_table.keys()))
                for key in all_keys:
                    if key in initial_table and key not in current_table:
                        row = initial_table[key]
                        for idx, value in enumerate(row):
                            differences.append((table, key, idx+1, columns[idx] if idx < len(columns) else f"Column {idx+1}", str(value), ""))
                    elif key in current_table and key not in initial_table:
                        row = current_table[key]
                        for idx, value in enumerate(row):
                            differences.append((table, key, idx+1, columns[idx] if idx < len(columns) else f"Column {idx+1}", "", str(value)))
                    elif key in initial_table and key in current_table:
                        row_initial = initial_table[key]
                        row_current = current_table[key]
                        for idx, (val_initial, val_current) in enumerate(zip(row_initial, row_current)):
                            if val_initial != val_current:
                                differences.append((table, key, idx+1, columns[idx] if idx < len(columns) else f"Column {idx+1}", str(val_initial), str(val_current)))
            self.root.after(0, lambda: self.display_differences(differences))
            self.root.after(0, lambda: messagebox.showinfo("Database Comparer", "Database comparison complete."))
        except Exception as e:
            self.root.after(0, lambda: messagebox.showerror("Database Comparer", f"Error comparing states:\n{str(e)}"))
    def display_differences(self, differences):
        self.result_table.delete(*self.result_table.get_children())
        for diff in differences:
            table, rec, col_num, col_name, old_val, new_val = diff
            display_old = old_val if len(old_val) <= 50 else old_val[:50] + "..."
            display_new = new_val if len(new_val) <= 50 else new_val[:50] + "..."
            self.result_table.insert("", "end", values=(table, rec, col_num, col_name, display_old, display_new))
    def show_full_value(self, event):
        region = self.result_table.identify("region", event.x, event.y)
        if region != "cell":
            return
        row_id = self.result_table.identify_row(event.y)
        col = self.result_table.identify_column(event.x)
        item = self.result_table.item(row_id)
        col_index = int(col.replace("#", "")) - 1
        if col_index < 0 or col_index >= len(self.columns):
            return
        value = item["values"][col_index]
        top = tk.Toplevel(self.root)
        top.title("Full Value")
        text = tk.Text(top, wrap="none")
        text.insert("1.0", value)
        text.config(state="disabled")
        text.pack(fill="both", expand=True)
        scrollbar_y = ttk.Scrollbar(top, orient="vertical", command=text.yview)
        scrollbar_y.pack(side="right", fill="y")
        text.config(yscrollcommand=scrollbar_y.set)
        scrollbar_x = ttk.Scrollbar(top, orient="horizontal", command=text.xview)
        scrollbar_x.pack(side="bottom", fill="x")
        text.config(xscrollcommand=scrollbar_x.set)
    def export_to_csv(self):
        if not self.result_table.get_children():
            messagebox.showinfo("Database Comparer", "No results to export.")
            return
        try:
            filename = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV Files", "*.csv")])
            if not filename:
                return
            with open(filename, "w", newline="") as csvfile:
                writer = csv.writer(csvfile)
                writer.writerow(["Table", "ID (First Column Value)", "Column Number", "Column Name", "Old Value", "New Value"])
                for item in self.result_table.get_children():
                    row = self.result_table.item(item)["values"]
                    writer.writerow(row)
            messagebox.showinfo("Database Comparer", f"Results exported to {filename} successfully.")
        except Exception as e:
            messagebox.showerror("Database Comparer", f"Error exporting CSV:\n{str(e)}")
    def clear_all(self):
        self.initial_state = {}
        self.current_state = {}
        self.result_table.delete(*self.result_table.get_children())

if __name__ == "__main__":
    root = tk.Tk()
    app = DatabaseComparer(root)
    root.mainloop()

