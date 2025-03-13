#!/usr/bin/python3

import mysql.connector
from mysql.connector import pooling
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import csv
import configparser
import os
import threading
import json
from io import StringIO
import re
from functools import partial
import time
import sys

class DatabaseModel:
    def __init__(self, config_path=None):
        self.script_directory = os.path.dirname(os.path.abspath(__file__))
        self.config_path = config_path if config_path is not None else os.path.join(self.script_directory, 'config.ini')
        self.config = self.load_config(self.config_path)
        self.column_cache = {}
        self.connection_pool = self._create_connection_pool()
        
    def load_config(self, config_path=None):
        config = configparser.ConfigParser()
        if config_path is None:
            config_path = os.path.join(self.script_directory, 'config.ini')
        config.read(config_path)
        return {
            'host': config['mysql']['host'],
            'user': config['mysql']['user'],
            'password': config['mysql']['password'],
            'database': config['mysql']['database'],
            'pool_name': 'db_pool',
            'pool_size': int(config['mysql'].get('pool_size', 5))
        }
    
    def reload_config(self):
        self.config = self.load_config(self.config_path)
        self.column_cache = {}
        self.connection_pool = self._create_connection_pool()
        return self.config
    
    def _create_connection_pool(self):
        try:
            pool_config = {
                'pool_name': self.config['pool_name'],
                'pool_size': self.config['pool_size'],
                'host': self.config['host'],
                'user': self.config['user'],
                'password': self.config['password'],
                'database': self.config['database']
            }
            return mysql.connector.pooling.MySQLConnectionPool(**pool_config)
        except Exception as e:
            print(f"Error creating connection pool: {e}")
            return None
    
    def get_connection(self):
        if self.connection_pool:
            try:
                return self.connection_pool.get_connection()
            except:
                pass
        return mysql.connector.connect(
            host=self.config['host'],
            user=self.config['user'],
            password=self.config['password'],
            database=self.config['database']
        )
    
    def get_tables(self):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("SHOW TABLES")
        tables = [t[0] for t in cursor.fetchall()]
        cursor.close()
        conn.close()
        return tables
    
    def get_table_columns(self, table):
        if table in self.column_cache:
            return self.column_cache[table]
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute(f"SHOW COLUMNS FROM {table}")
        columns = [col[0] for col in cursor.fetchall()]
        cursor.close()
        conn.close()
        self.column_cache[table] = columns
        return columns
    
    def fetch_table_state_fast(self, table, callback=None, stop_event=None):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute(f"SELECT COUNT(*) FROM {table}")
        total_rows = cursor.fetchone()[0]
        columns = self.get_table_columns(table)
        cursor.execute(f"SELECT * FROM {table}")
        all_rows = cursor.fetchall()
        state = {}
        for row in all_rows:
            if stop_event and stop_event.is_set():
                cursor.close()
                conn.close()
                return None, None
            key = row[0]
            state[key] = row
        if callback:
            callback(table, total_rows, total_rows)
        cursor.close()
        conn.close()
        return state, columns
    
    def fetch_table_state(self, table, batch_size=1000, callback=None, stop_event=None):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute(f"SELECT COUNT(*) FROM {table}")
        total_rows = cursor.fetchone()[0]
        columns = self.get_table_columns(table)
        state = {}
        offset = 0
        processed = 0
        while True:
            if stop_event and stop_event.is_set():
                cursor.close()
                conn.close()
                return None, None
            cursor.execute(f"SELECT * FROM {table} LIMIT {batch_size} OFFSET {offset}")
            batch = cursor.fetchall()
            if not batch:
                break
            for row in batch:
                key = row[0]
                state[key] = row
            processed += len(batch)
            offset += batch_size
            if callback:
                callback(table, processed, total_rows)
            if len(batch) < batch_size:
                break
        cursor.close()
        conn.close()
        return state, columns
    
    def fetch_specific_tables_state(self, tables, batch_size=1000, progress_callback=None, fast_mode=False, stop_event=None):
        all_states = {}
        all_columns = {}
        for i, table in enumerate(tables):
            if stop_event and stop_event.is_set():
                return None, None
            if progress_callback:
                progress_callback(f"Fetching {table}...", i, len(tables))
            if fast_mode:
                state, columns = self.fetch_table_state_fast(
                    table, 
                    callback=lambda t, p, total: progress_callback(
                        f"Fetching {t}...", i, len(tables), p / (total if total > 0 else 1)
                    ) if progress_callback else None,
                    stop_event=stop_event
                )
            else:
                state, columns = self.fetch_table_state(
                    table, 
                    batch_size=batch_size,
                    callback=lambda t, p, total: progress_callback(
                        f"Fetching {t}...", i, len(tables), p / (total if total > 0 else 1)
                    ) if progress_callback else None,
                    stop_event=stop_event
                )
            if state is None and columns is None:
                return None, None
            all_states[table] = state
            all_columns[table] = columns
        return all_states, all_columns

class DatabaseController:
    def __init__(self, model):
        self.model = model
        self.initial_state = {}
        self.initial_columns = {}
        self.current_state = {}
        self.current_columns = {}
        self.selected_tables = None
        self.fast_mode = False
        self.stop_event = threading.Event()
        
    def fetch_initial_state(self, batch_size=1000, progress_callback=None):
        self.stop_event.clear()
        tables = self.selected_tables or self.model.get_tables()
        self.initial_state, self.initial_columns = self.model.fetch_specific_tables_state(
            tables, batch_size, progress_callback, fast_mode=self.fast_mode, stop_event=self.stop_event
        )
        if self.initial_state is None and self.initial_columns is None:
            return None, None
        return self.initial_state, self.initial_columns
    
    def fetch_current_state(self, batch_size=1000, progress_callback=None):
        self.stop_event.clear()
        tables = self.selected_tables or self.model.get_tables()
        self.current_state, self.current_columns = self.model.fetch_specific_tables_state(
            tables, batch_size, progress_callback, fast_mode=self.fast_mode, stop_event=self.stop_event
        )
        if self.current_state is None and self.current_columns is None:
            return None, None
        return self.current_state, self.current_columns
    
    def compare_states_fast(self, progress_callback=None):
        self.stop_event.clear()
        if not self.initial_state:
            raise ValueError("Initial state not fetched")
        differences = []
        all_tables = set(list(self.initial_state.keys()) + list(self.current_state.keys()))
        total_tables = len(all_tables)
        for i, table in enumerate(all_tables):
            if self.stop_event.is_set():
                return None
            if progress_callback:
                progress_callback(f"Comparing {table}...", i, total_tables)
            columns = (self.initial_columns.get(table) or 
                       self.current_columns.get(table) or 
                       self.model.get_table_columns(table))
            initial_table = self.initial_state.get(table, {})
            current_table = self.current_state.get(table, {})
            initial_keys = set(initial_table.keys())
            current_keys = set(current_table.keys())
            deleted_keys = initial_keys - current_keys
            added_keys = current_keys - initial_keys
            common_keys = initial_keys & current_keys
            if progress_callback:
                progress_callback(f"Processing deleted rows in {table}...", i, total_tables, 0.25)
            if self.stop_event.is_set():
                return None
            for key in deleted_keys:
                row = initial_table[key]
                for idx, value in enumerate(row):
                    col_name = columns[idx] if idx < len(columns) else f"Column {idx+1}"
                    differences.append({
                        'table': table,
                        'id': key,
                        'column_number': idx+1,
                        'column_name': col_name,
                        'old_value': str(value) if value is not None else '',
                        'new_value': '',
                        'change_type': 'deleted'
                    })
            if progress_callback:
                progress_callback(f"Processing added rows in {table}...", i, total_tables, 0.5)
            if self.stop_event.is_set():
                return None
            for key in added_keys:
                row = current_table[key]
                for idx, value in enumerate(row):
                    col_name = columns[idx] if idx < len(columns) else f"Column {idx+1}"
                    differences.append({
                        'table': table,
                        'id': key,
                        'column_number': idx+1,
                        'column_name': col_name,
                        'old_value': '',
                        'new_value': str(value) if value is not None else '',
                        'change_type': 'added'
                    })
            if progress_callback:
                progress_callback(f"Processing modified rows in {table}...", i, total_tables, 0.75)
            for j, key in enumerate(common_keys):
                if j % 1000 == 0 and self.stop_event.is_set():
                    return None
                row_initial = initial_table[key]
                row_current = current_table[key]
                for idx, (val_initial, val_current) in enumerate(zip(row_initial, row_current)):
                    str_val_initial = str(val_initial) if val_initial is not None else ''
                    str_val_current = str(val_current) if val_current is not None else ''
                    if str_val_initial != str_val_current:
                        col_name = columns[idx] if idx < len(columns) else f"Column {idx+1}"
                        differences.append({
                            'table': table,
                            'id': key,
                            'column_number': idx+1,
                            'column_name': col_name,
                            'old_value': str_val_initial,
                            'new_value': str_val_current,
                            'change_type': 'modified'
                        })
                if progress_callback and j % 1000 == 0 and len(common_keys) > 0:
                    sub_progress = 0.75 + (0.25 * j / len(common_keys))
                    progress_callback(f"Processing modified rows in {table}...", i, total_tables, sub_progress)
        return differences
    
    def compare_states(self, progress_callback=None):
        self.stop_event.clear()
        if self.fast_mode:
            return self.compare_states_fast(progress_callback)
        if not self.initial_state:
            raise ValueError("Initial state not fetched")
        differences = []
        all_tables = set(list(self.initial_state.keys()) + list(self.current_state.keys()))
        total_tables = len(all_tables)
        for i, table in enumerate(all_tables):
            if self.stop_event.is_set():
                return None
            if progress_callback:
                progress_callback(f"Comparing {table}...", i, total_tables)
            columns = (self.initial_columns.get(table) or 
                      self.current_columns.get(table) or 
                      self.model.get_table_columns(table))
            initial_table = self.initial_state.get(table, {})
            current_table = self.current_state.get(table, {})
            all_keys = set(list(initial_table.keys()) + list(current_table.keys()))
            total_keys = len(all_keys)
            for j, key in enumerate(all_keys):
                if j % 100 == 0 and self.stop_event.is_set():
                    return None
                if progress_callback and j % 100 == 0:
                    sub_progress = j / total_keys if total_keys > 0 else 1
                    progress_callback(f"Comparing {table}...", i + sub_progress, total_tables)
                if key in initial_table and key not in current_table:
                    row = initial_table[key]
                    for idx, value in enumerate(row):
                        col_name = columns[idx] if idx < len(columns) else f"Column {idx+1}"
                        differences.append({
                            'table': table,
                            'id': key,
                            'column_number': idx+1,
                            'column_name': col_name,
                            'old_value': str(value) if value is not None else '',
                            'new_value': '',
                            'change_type': 'deleted'
                        })
                elif key in current_table and key not in initial_table:
                    row = current_table[key]
                    for idx, value in enumerate(row):
                        col_name = columns[idx] if idx < len(columns) else f"Column {idx+1}"
                        differences.append({
                            'table': table,
                            'id': key,
                            'column_number': idx+1,
                            'column_name': col_name,
                            'old_value': '',
                            'new_value': str(value) if value is not None else '',
                            'change_type': 'added'
                        })
                elif key in initial_table and key in current_table:
                    row_initial = initial_table[key]
                    row_current = current_table[key]
                    for idx, (val_initial, val_current) in enumerate(zip(row_initial, row_current)):
                        str_val_initial = str(val_initial) if val_initial is not None else ''
                        str_val_current = str(val_current) if val_current is not None else ''
                        if str_val_initial != str_val_current:
                            col_name = columns[idx] if idx < len(columns) else f"Column {idx+1}"
                            differences.append({
                                'table': table,
                                'id': key,
                                'column_number': idx+1,
                                'column_name': col_name,
                                'old_value': str_val_initial,
                                'new_value': str_val_current,
                                'change_type': 'modified'
                            })
        return differences
    
    def request_stop(self):
        self.stop_event.set()
    
    def clear_states(self):
        self.initial_state = {}
        self.initial_columns = {}
        self.current_state = {}
        self.current_columns = {}
    
    def set_selected_tables(self, tables):
        self.selected_tables = tables
        
    def set_fast_mode(self, enabled):
        self.fast_mode = enabled

class DatabaseCompareView(tk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent)
        self.parent = parent
        self.controller = controller
        self.result_data = []
        self.sort_column = None
        self.sort_order = True
        self.page_size = 100
        self.current_page = 0
        self.filtered_data = []
        self.filter_text = ""
        self.selected_tables = None
        self.fast_mode = tk.BooleanVar(value=False)
        self.is_operation_running = False
        parent.title(f"Database Comparer: {controller.model.config['database']}")
        self.create_widgets()
        self.create_menu()
        style = ttk.Style()
        try:
            style.theme_use('clam')
            style.configure("Treeview", background="#f9f9f9", fieldbackground="#f9f9f9", foreground="black")
            style.map('Treeview', background=[('selected', '#0078D7')])
            style.configure("Treeview.Heading", background="#e1e1e1", foreground="black", relief="flat")
            style.map("Treeview.Heading", background=[('active', '#d0d0d0')])
            style.configure("Stop.TButton", background="#ff5252", foreground="white")
        except:
            pass
        
    def create_menu(self):
        menubar = tk.Menu(self.parent)
        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="Export to CSV File...", command=self.export_to_csv_file)
        file_menu.add_command(label="Export to Clipboard", command=self.export_to_clipboard)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.parent.quit)
        menubar.add_cascade(label="File", menu=file_menu)
        view_menu = tk.Menu(menubar, tearoff=0)
        view_menu.add_command(label="Refresh", command=self.refresh_view)
        view_menu.add_separator()
        page_menu = tk.Menu(view_menu, tearoff=0)
        for size in [50, 100, 200, 500, 1000]:
            page_menu.add_command(label=f"{size} rows", command=lambda s=size: self.set_page_size(s))
        view_menu.add_cascade(label="Page Size", menu=page_menu)
        menubar.add_cascade(label="View", menu=view_menu)
        options_menu = tk.Menu(menubar, tearoff=0)
        options_menu.add_command(label="Select Tables...", command=self.select_tables)
        options_menu.add_command(label="Settings...", command=self.show_settings)
        options_menu.add_separator()
        options_menu.add_command(label="Reload App", command=self.reload_app)
        menubar.add_cascade(label="Options", menu=options_menu)
        help_menu = tk.Menu(menubar, tearoff=0)
        help_menu.add_command(label="About", command=self.show_about)
        menubar.add_cascade(label="Help", menu=help_menu)
        self.parent.config(menu=menubar)
    
    def create_widgets(self):
        main_frame = ttk.Frame(self)
        main_frame.pack(fill="both", expand=True, padx=10, pady=10)
        self.button_frame = ttk.Frame(main_frame)
        self.button_frame.pack(fill="x", pady=(0, 10))
        self.fetch_state_button = ttk.Button(self.button_frame, text="Fetch State", command=self.on_fetch_state)
        self.fetch_state_button.pack(side="left", padx=5)
        self.compare_states_button = ttk.Button(self.button_frame, text="Compare States", command=self.on_compare_states)
        self.compare_states_button.pack(side="left", padx=5)
        self.export_csv_button = ttk.Button(self.button_frame, text="Copy CSV to Clipboard", command=self.export_to_clipboard)
        self.export_csv_button.pack(side="left", padx=5)
        self.clear_all_button = ttk.Button(self.button_frame, text="Clear All", command=self.clear_all)
        self.clear_all_button.pack(side="left", padx=5)
        self.stop_button = ttk.Button(self.button_frame, text="STOP", style="Stop.TButton", command=self.stop_operations)
        self.stop_button.pack(side="left", padx=5)
        self.fast_mode_check = ttk.Checkbutton(self.button_frame, text="FAST MODE [HIGH RAM USAGE!]", variable=self.fast_mode, command=self.toggle_fast_mode)
        self.fast_mode_check.pack(side="right", padx=5)
        self.filter_frame = ttk.Frame(main_frame)
        self.filter_frame.pack(fill="x", pady=(0, 10))
        ttk.Label(self.filter_frame, text="Filter:").pack(side="left", padx=(0, 5))
        self.filter_var = tk.StringVar()
        self.filter_var.trace("w", self.on_filter_changed)
        self.filter_entry = ttk.Entry(self.filter_frame, textvariable=self.filter_var, width=30)
        self.filter_entry.pack(side="left", fill="x", expand=True, padx=(0, 5))
        self.filter_column_var = tk.StringVar(value="All Columns")
        self.filter_column_combo = ttk.Combobox(self.filter_frame, textvariable=self.filter_column_var, values=["All Columns", "Table", "ID", "Column Name", "Old Value", "New Value"], state="readonly", width=15)
        self.filter_column_combo.pack(side="left", padx=5)
        self.filter_column_combo.bind("<<ComboboxSelected>>", lambda e: self.apply_filter())
        self.status_var = tk.StringVar(value="Ready")
        self.status_bar = ttk.Label(main_frame, textvariable=self.status_var, relief="sunken", anchor="w")
        self.status_bar.pack(side="bottom", fill="x")
        self.progress_var = tk.DoubleVar(value=0)
        self.progress_bar = ttk.Progressbar(main_frame, orient="horizontal", mode="determinate", variable=self.progress_var)
        self.progress_bar.pack(side="bottom", fill="x", pady=(5, 0))
        self.tree_frame = ttk.Frame(main_frame)
        self.tree_frame.pack(fill="both", expand=True)
        self.columns = ("table", "id", "column_number", "column_name", "old_value", "new_value")
        self.result_tree = ttk.Treeview(self.tree_frame, columns=self.columns, show="headings", selectmode="browse")
        self.result_tree.heading("table", text="Table", command=lambda: self.sort_by_column("table"))
        self.result_tree.heading("id", text="ID (First Column Value)", command=lambda: self.sort_by_column("id"))
        self.result_tree.heading("column_number", text="Column Number", command=lambda: self.sort_by_column("column_number"))
        self.result_tree.heading("column_name", text="Column Name", command=lambda: self.sort_by_column("column_name"))
        self.result_tree.heading("old_value", text="Old Value", command=lambda: self.sort_by_column("old_value"))
        self.result_tree.heading("new_value", text="New Value", command=lambda: self.sort_by_column("new_value"))
        self.result_tree.column("table", width=100, minwidth=80)
        self.result_tree.column("id", width=150, minwidth=100)
        self.result_tree.column("column_number", width=60, minwidth=60)
        self.result_tree.column("column_name", width=150, minwidth=100)
        self.result_tree.column("old_value", width=200, minwidth=150)
        self.result_tree.column("new_value", width=200, minwidth=150)
        y_scrollbar = ttk.Scrollbar(self.tree_frame, orient="vertical", command=self.result_tree.yview)
        y_scrollbar.pack(side="right", fill="y")
        x_scrollbar = ttk.Scrollbar(self.tree_frame, orient="horizontal", command=self.result_tree.xview)
        x_scrollbar.pack(side="bottom", fill="x")
        self.result_tree.configure(yscrollcommand=y_scrollbar.set, xscrollcommand=x_scrollbar.set)
        self.result_tree.pack(side="left", fill="both", expand=True)
        self.result_tree.bind("<Double-1>", self.show_full_value)
        self.result_tree.tag_configure('added', background='#e6ffe6')
        self.result_tree.tag_configure('modified', background='#fff0e6')
        self.result_tree.tag_configure('deleted', background='#ffe6e6')
        self.pagination_frame = ttk.Frame(main_frame)
        self.pagination_frame.pack(fill="x", pady=(5, 0), before=self.status_bar)
        self.prev_page_button = ttk.Button(self.pagination_frame, text="◀ Previous", command=self.prev_page, state="disabled")
        self.prev_page_button.pack(side="left")
        self.page_label_var = tk.StringVar(value="Page 1 of 1")
        self.page_label = ttk.Label(self.pagination_frame, textvariable=self.page_label_var, width=20, anchor="center")
        self.page_label.pack(side="left", padx=10)
        self.next_page_button = ttk.Button(self.pagination_frame, text="Next ▶", command=self.next_page, state="disabled")
        self.next_page_button.pack(side="left")
        self.page_info_var = tk.StringVar(value="0 differences found")
        self.page_info_label = ttk.Label(self.pagination_frame, textvariable=self.page_info_var, anchor="e")
        self.page_info_label.pack(side="right")
        self.pack(fill="both", expand=True)
    
    def stop_operations(self):
        if self.is_operation_running:
            self.controller.request_stop()
            self.status_var.set("Stopping current operation...")
    
    def reload_app(self):
        if messagebox.askyesno("Reload Application", "Are you sure you want to reload the application?"):
            geometry = self.parent.geometry()
            with open('temp_geometry.txt', 'w') as f:
                f.write(geometry)
            python = sys.executable
            os.execl(python, python, *sys.argv)
    
    def toggle_fast_mode(self):
        is_enabled = self.fast_mode.get()
        self.controller.set_fast_mode(is_enabled)
        if is_enabled:
            self.status_var.set("FAST MODE enabled - will load entire database into RAM")
        else:
            self.status_var.set("Normal mode enabled - using batched processing")
    
    def on_fetch_state(self):
        if self.is_operation_running:
            messagebox.showinfo("Operation in Progress", "An operation is already running. Please wait or click STOP.")
            return
        if self.controller.initial_state:
            response = messagebox.askyesno("Confirm Action", "This will overwrite the existing initial state. Continue?")
            if not response:
                return
        self.is_operation_running = True
        self.set_buttons_state("disabled")
        self.status_var.set("Fetching database state...")
        self.progress_var.set(0)
        threading.Thread(target=self._fetch_state_thread).start()
    
    def _fetch_state_thread(self):
        try:
            result = self.controller.fetch_initial_state(progress_callback=self._update_progress)
            if result == (None, None):
                self.parent.after(0, self._operation_stopped)
                return
            self.parent.after(0, self._fetch_state_complete)
        except Exception as exc:
            error_message = str(exc)
            self.parent.after(0, lambda: self._show_error(f"Error fetching state: {error_message}"))
        finally:
            self.parent.after(0, lambda: setattr(self, 'is_operation_running', False))
    
    def _operation_stopped(self):
        self.set_buttons_state("normal")
        self.status_var.set("Operation stopped by user.")
        self.progress_var.set(0)
    
    def _fetch_state_complete(self):
        self.set_buttons_state("normal")
        self.status_var.set("Database state fetched successfully.")
        self.progress_var.set(100)
        messagebox.showinfo("Database Comparer", "Database state fetched successfully.")
    
    def on_compare_states(self):
        if self.is_operation_running:
            messagebox.showinfo("Operation in Progress", "An operation is already running. Please wait or click STOP.")
            return
        if not self.controller.initial_state:
            messagebox.showerror("Database Comparer", "Initial state not fetched. Use Fetch State button first.")
            return
        self.is_operation_running = True
        self.set_buttons_state("disabled")
        self.status_var.set("Comparing database states...")
        self.progress_var.set(0)
        threading.Thread(target=self._compare_states_thread).start()
    
    def _compare_states_thread(self):
        try:
            self.parent.after(0, lambda: self.status_var.set("Fetching current state..."))
            result = self.controller.fetch_current_state(progress_callback=self._update_progress)
            if result == (None, None):
                self.parent.after(0, self._operation_stopped)
                return
            self.parent.after(0, lambda: self.status_var.set("Comparing states..."))
            self.parent.after(0, lambda: self.progress_var.set(0))
            differences = self.controller.compare_states(progress_callback=self._update_progress)
            if differences is None:
                self.parent.after(0, self._operation_stopped)
                return
            self.result_data = differences
            self.filtered_data = differences
            self.parent.after(0, self._compare_states_complete)
        except Exception as exc:
            error_message = str(exc)
            self.parent.after(0, lambda: self._show_error(f"Error comparing states: {error_message}"))
        finally:
            self.parent.after(0, lambda: setattr(self, 'is_operation_running', False))
    
    def _compare_states_complete(self):
        self.set_buttons_state("normal")
        self.status_var.set(f"Comparison complete. Found {len(self.result_data)} differences.")
        self.progress_var.set(100)
        self.apply_filter()
        self.current_page = 0
        self.update_pagination()
        self.display_page()
        messagebox.showinfo("Database Comparer", f"Database comparison complete. Found {len(self.result_data)} differences.")
    
    def display_page(self):
        self.result_tree.delete(*self.result_tree.get_children())
        if not self.filtered_data:
            return
        start_idx = self.current_page * self.page_size
        end_idx = min(start_idx + self.page_size, len(self.filtered_data))
        for i in range(start_idx, end_idx):
            diff = self.filtered_data[i]
            values = (
                diff['table'],
                diff['id'],
                diff['column_number'],
                diff['column_name'],
                self._truncate_value(diff['old_value']),
                self._truncate_value(diff['new_value'])
            )
            self.result_tree.insert("", "end", values=values, tags=(diff.get('change_type', ''),))
    
    def _truncate_value(self, value, max_length=50):
        if len(value) <= max_length:
            return value
        return value[:max_length] + "..."
    
    def update_pagination(self):
        total_items = len(self.filtered_data)
        total_pages = max(1, (total_items + self.page_size - 1) // self.page_size)
        current_page = min(self.current_page + 1, total_pages)
        self.page_label_var.set(f"Page {current_page} of {total_pages}")
        self.page_info_var.set(f"{total_items} differences found")
        self.prev_page_button.config(state="normal" if self.current_page > 0 else "disabled")
        self.next_page_button.config(state="normal" if self.current_page < total_pages - 1 else "disabled")
    
    def next_page(self):
        total_pages = (len(self.filtered_data) + self.page_size - 1) // self.page_size
        if self.current_page < total_pages - 1:
            self.current_page += 1
            self.update_pagination()
            self.display_page()
    
    def prev_page(self):
        if self.current_page > 0:
            self.current_page -= 1
            self.update_pagination()
            self.display_page()
    
    def set_page_size(self, size):
        self.page_size = size
        self.current_page = 0
        self.update_pagination()
        self.display_page()
    
    def sort_by_column(self, column):
        column_index = self.columns.index(column)
        if self.sort_column == column:
            self.sort_order = not self.sort_order
        else:
            self.sort_column = column
            self.sort_order = True
        self.filtered_data.sort(key=lambda x: (str(x[column]) if column != 'column_number' else int(x[column])), reverse=not self.sort_order)
        self.current_page = 0
        self.update_pagination()
        self.display_page()
    
    def on_filter_changed(self, *args):
        if hasattr(self, '_filter_timer'):
            self.parent.after_cancel(self._filter_timer)
        self._filter_timer = self.parent.after(300, self.apply_filter)
    
    def apply_filter(self):
        filter_text = self.filter_var.get().lower()
        filter_column = self.filter_column_var.get()
        if not filter_text:
            self.filtered_data = self.result_data
        else:
            if filter_column == "All Columns":
                self.filtered_data = [
                    diff for diff in self.result_data if
                    filter_text in str(diff['table']).lower() or
                    filter_text in str(diff['id']).lower() or
                    filter_text in str(diff['column_name']).lower() or
                    filter_text in str(diff['old_value']).lower() or
                    filter_text in str(diff['new_value']).lower()
                ]
            else:
                column_map = {
                    "Table": "table",
                    "ID": "id",
                    "Column Name": "column_name",
                    "Old Value": "old_value",
                    "New Value": "new_value"
                }
                field = column_map.get(filter_column)
                if field:
                    self.filtered_data = [
                        diff for diff in self.result_data if
                        filter_text in str(diff[field]).lower()
                    ]
        self.current_page = 0
        self.update_pagination()
        self.display_page()
    
    def show_full_value(self, event):
        region = self.result_tree.identify("region", event.x, event.y)
        if region != "cell":
            return
        item_id = self.result_tree.identify_row(event.y)
        if not item_id:
            return
        column_id = self.result_tree.identify_column(event.x)
        if not column_id:
            return
        col_idx = int(column_id.replace("#", "")) - 1
        column_name = self.columns[col_idx]
        if column_name not in ("old_value", "new_value"):
            return
        item_idx = self.result_tree.index(item_id)
        page_start = self.current_page * self.page_size
        data_idx = page_start + item_idx
        if data_idx >= len(self.filtered_data):
            return
        full_value = self.filtered_data[data_idx][column_name]
        self.show_value_dialog(full_value, column_name.replace("_", " ").title())
    
    def show_value_dialog(self, value, title):
        dialog = tk.Toplevel(self.parent)
        dialog.title(title)
        dialog.geometry("600x400")
        dialog.minsize(400, 300)
        dialog.transient(self.parent)
        frame = ttk.Frame(dialog)
        frame.pack(fill="both", expand=True, padx=10, pady=10)
        text = tk.Text(frame, wrap="none")
        y_scrollbar = ttk.Scrollbar(frame, orient="vertical", command=text.yview)
        y_scrollbar.pack(side="right", fill="y")
        x_scrollbar = ttk.Scrollbar(frame, orient="horizontal", command=text.xview)
        x_scrollbar.pack(side="bottom", fill="x")
        text.pack(side="left", fill="both", expand=True)
        text.config(yscrollcommand=y_scrollbar.set, xscrollcommand=x_scrollbar.set)
        text.insert("1.0", value)
        button_frame = ttk.Frame(dialog)
        button_frame.pack(fill="x", pady=10)
        copy_button = ttk.Button(button_frame, text="Copy to Clipboard", command=lambda: self.copy_to_clipboard(value, dialog))
        copy_button.pack(side="left", padx=5)
        close_button = ttk.Button(button_frame, text="Close", command=dialog.destroy)
        close_button.pack(side="right", padx=5)
        if re.match(r'^\s*\{.*\}\s*$', value) or re.match(r'^\s*\[.*\]\s*$', value):
            try:
                json_obj = json.loads(value)
                formatted_json = json.dumps(json_obj, indent=2)
                text.delete("1.0", "end")
                text.insert("1.0", formatted_json)
            except:
                pass
        dialog.update_idletasks()
        dialog.after(100, lambda: dialog.grab_set())
    
    def copy_to_clipboard(self, text, dialog=None):
        self.parent.clipboard_clear()
        self.parent.clipboard_append(text)
        if dialog:
            dialog.destroy()
            messagebox.showinfo("Clipboard", "Text copied to clipboard.")
    
    def export_to_clipboard(self):
        if not self.result_data:
            messagebox.showinfo("Database Comparer", "No results to export.")
            return
        try:
            output = StringIO()
            writer = csv.writer(output)
            writer.writerow([
                "Table", 
                "ID (First Column Value)", 
                "Column Number", 
                "Column Name", 
                "Old Value", 
                "New Value",
                "Change Type"
            ])
            for row in self.filtered_data:
                writer.writerow([
                    row['table'],
                    row['id'],
                    row['column_number'],
                    row['column_name'],
                    row['old_value'],
                    row['new_value'],
                    row.get('change_type', '')
                ])
            csv_content = output.getvalue()
            self.parent.clipboard_clear()
            self.parent.clipboard_append(csv_content)
            output.close()
            messagebox.showinfo("Database Comparer", "CSV copied to clipboard successfully.")
        except Exception as e:
            self._show_error(f"Error exporting CSV: {str(e)}")
    
    def export_to_csv_file(self):
        if not self.result_data:
            messagebox.showinfo("Database Comparer", "No results to export.")
            return
        try:
            filename = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV files", "*.csv"), ("All files", "*.*")])
            if not filename:
                return
            with open(filename, 'w', newline='') as csvfile:
                writer = csv.writer(csvfile)
                writer.writerow([
                    "Table", 
                    "ID (First Column Value)", 
                    "Column Number", 
                    "Column Name", 
                    "Old Value", 
                    "New Value",
                    "Change Type"
                ])
                for row in self.filtered_data:
                    writer.writerow([
                        row['table'],
                        row['id'],
                        row['column_number'],
                        row['column_name'],
                        row['old_value'],
                        row['new_value'],
                        row.get('change_type', '')
                    ])
            messagebox.showinfo("Database Comparer", f"Data exported to {filename} successfully.")
        except Exception as e:
            self._show_error(f"Error exporting CSV: {str(e)}")
    
    def clear_all(self):
        if self.result_data and messagebox.askyesno("Confirm Clear", "This will clear all fetched data and results. Continue?"):
            self.controller.clear_states()
            self.result_data = []
            self.filtered_data = []
            self.result_tree.delete(*self.result_tree.get_children())
            self.filter_var.set("")
            self.current_page = 0
            self.update_pagination()
            self.status_var.set("Ready")
            self.progress_var.set(0)
    
    def select_tables(self):
        dialog = tk.Toplevel(self.parent)
        dialog.title("Select Tables")
        dialog.geometry("400x500")
        dialog.minsize(300, 400)
        dialog.transient(self.parent)
        dialog.grab_set()
        search_frame = ttk.Frame(dialog)
        search_frame.pack(fill="x", padx=10, pady=5)
        ttk.Label(search_frame, text="Search:").pack(side="left")
        search_var = tk.StringVar()
        search_entry = ttk.Entry(search_frame, textvariable=search_var)
        search_entry.pack(side="left", fill="x", expand=True, padx=5)
        list_frame = ttk.Frame(dialog)
        list_frame.pack(fill="both", expand=True, padx=10, pady=5)
        tables = sorted(self.controller.model.get_tables())
        table_vars = {}
        canvas = tk.Canvas(list_frame)
        scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=canvas.yview)
        scrollbar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        canvas.configure(yscrollcommand=scrollbar.set)
        check_frame = ttk.Frame(canvas)
        canvas.create_window((0, 0), window=check_frame, anchor="nw")
        select_all_var = tk.BooleanVar(value=False)
        def toggle_all():
            for var in table_vars.values():
                var.set(select_all_var.get())
        select_all_check = ttk.Checkbutton(check_frame, text="Select All", variable=select_all_var, command=toggle_all)
        select_all_check.pack(anchor="w", padx=5, pady=5)
        ttk.Separator(check_frame).pack(fill="x", padx=5, pady=2)
        for table in tables:
            var = tk.BooleanVar(value=False)
            table_vars[table] = var
            if self.controller.selected_tables and table in self.controller.selected_tables:
                var.set(True)
            ttk.Checkbutton(check_frame, text=table, variable=var).pack(anchor="w", padx=5, pady=2)
        def on_frame_configure(event):
            canvas.configure(scrollregion=canvas.bbox("all"))
        check_frame.bind("<Configure>", on_frame_configure)
        def filter_tables(*args):
            search_text = search_var.get().lower()
            for table in tables:
                if search_text and search_text not in table.lower():
                    for widget in check_frame.winfo_children():
                        if isinstance(widget, ttk.Checkbutton) and widget.cget("text") == table:
                            widget.pack_forget()
                else:
                    shown = False
                    for widget in check_frame.winfo_children():
                        if isinstance(widget, ttk.Checkbutton) and widget.cget("text") == table:
                            if not widget.winfo_viewable():
                                widget.pack(anchor="w", padx=5, pady=2)
                            shown = True
                    if not shown and table != "Select All":
                        ttk.Checkbutton(check_frame, text=table, variable=table_vars[table]).pack(anchor="w", padx=5, pady=2)
        search_var.trace("w", filter_tables)
        button_frame = ttk.Frame(dialog)
        button_frame.pack(fill="x", padx=10, pady=10)
        def apply_selection():
            selected = [table for table, var in table_vars.items() if var.get()]
            if not selected:
                messagebox.showwarning("Table Selection", "No tables selected. All tables will be used.")
                self.controller.set_selected_tables(None)
            else:
                self.controller.set_selected_tables(selected)
                self.status_var.set(f"Selected {len(selected)} tables for comparison")
            dialog.destroy()
        ttk.Button(button_frame, text="Apply", command=apply_selection).pack(side="right", padx=5)
        ttk.Button(button_frame, text="Cancel", command=dialog.destroy).pack(side="right", padx=5)
        if self.controller.selected_tables:
            for table in self.controller.selected_tables:
                if table in table_vars:
                    table_vars[table].set(True)
            all_selected = all(var.get() for var in table_vars.values())
            select_all_var.set(all_selected)
    
    def show_settings(self):
        dialog = tk.Toplevel(self.parent)
        dialog.title("Settings")
        dialog.geometry("400x300")
        dialog.minsize(300, 250)
        dialog.transient(self.parent)
        dialog.grab_set()
        notebook = ttk.Notebook(dialog)
        notebook.pack(fill="both", expand=True, padx=10, pady=10)
        db_frame = ttk.Frame(notebook)
        notebook.add(db_frame, text="Database")
        ttk.Label(db_frame, text="Host:").grid(row=0, column=0, sticky="w", padx=5, pady=5)
        host_var = tk.StringVar(value=self.controller.model.config['host'])
        ttk.Entry(db_frame, textvariable=host_var).grid(row=0, column=1, sticky="ew", padx=5, pady=5)
        ttk.Label(db_frame, text="Database:").grid(row=1, column=0, sticky="w", padx=5, pady=5)
        db_var = tk.StringVar(value=self.controller.model.config['database'])
        ttk.Entry(db_frame, textvariable=db_var).grid(row=1, column=1, sticky="ew", padx=5, pady=5)
        ttk.Label(db_frame, text="User:").grid(row=2, column=0, sticky="w", padx=5, pady=5)
        user_var = tk.StringVar(value=self.controller.model.config['user'])
        ttk.Entry(db_frame, textvariable=user_var).grid(row=2, column=1, sticky="ew", padx=5, pady=5)
        ttk.Label(db_frame, text="Password:").grid(row=3, column=0, sticky="w", padx=5, pady=5)
        pass_var = tk.StringVar(value=self.controller.model.config['password'])
        ttk.Entry(db_frame, textvariable=pass_var, show="*").grid(row=3, column=1, sticky="ew", padx=5, pady=5)
        ttk.Label(db_frame, text="Connection Pool Size:").grid(row=4, column=0, sticky="w", padx=5, pady=5)
        pool_var = tk.StringVar(value=str(self.controller.model.config.get('pool_size', 5)))
        ttk.Entry(db_frame, textvariable=pool_var).grid(row=4, column=1, sticky="ew", padx=5, pady=5)
        db_frame.columnconfigure(1, weight=1)
        display_frame = ttk.Frame(notebook)
        notebook.add(display_frame, text="Display")
        ttk.Label(display_frame, text="Default Page Size:").grid(row=0, column=0, sticky="w", padx=5, pady=5)
        page_size_var = tk.StringVar(value=str(self.page_size))
        ttk.Combobox(display_frame, textvariable=page_size_var, values=["50", "100", "200", "500", "1000"], state="readonly").grid(row=0, column=1, sticky="ew", padx=5, pady=5)
        ttk.Label(display_frame, text="Added Row Color:").grid(row=1, column=0, sticky="w", padx=5, pady=5)
        added_color_var = tk.StringVar(value="#e6ffe6")
        ttk.Entry(display_frame, textvariable=added_color_var).grid(row=1, column=1, sticky="ew", padx=5, pady=5)
        ttk.Label(display_frame, text="Modified Row Color:").grid(row=2, column=0, sticky="w", padx=5, pady=5)
        modified_color_var = tk.StringVar(value="#fff0e6")
        ttk.Entry(display_frame, textvariable=modified_color_var).grid(row=2, column=1, sticky="ew", padx=5, pady=5)
        ttk.Label(display_frame, text="Deleted Row Color:").grid(row=3, column=0, sticky="w", padx=5, pady=5)
        deleted_color_var = tk.StringVar(value="#ffe6e6")
        ttk.Entry(display_frame, textvariable=deleted_color_var).grid(row=3, column=1, sticky="ew", padx=5, pady=5)
        display_frame.columnconfigure(1, weight=1)
        button_frame = ttk.Frame(dialog)
        button_frame.pack(fill="x", padx=10, pady=10)
        def save_settings():
            try:
                new_config = {
                    'host': host_var.get(),
                    'database': db_var.get(),
                    'user': user_var.get(),
                    'password': pass_var.get(),
                    'pool_size': int(pool_var.get())
                }
                config = configparser.ConfigParser()
                config['mysql'] = {
                    'host': new_config['host'],
                    'database': new_config['database'],
                    'user': new_config['user'],
                    'password': new_config['password'],
                    'pool_size': str(new_config['pool_size'])
                }
                config_path = os.path.join(self.controller.model.script_directory, 'config.ini')
                with open(config_path, 'w') as configfile:
                    config.write(configfile)
                self.controller.model.reload_config()
                self.page_size = int(page_size_var.get())
                self.result_tree.tag_configure('added', background=added_color_var.get())
                self.result_tree.tag_configure('modified', background=modified_color_var.get())
                self.result_tree.tag_configure('deleted', background=deleted_color_var.get())
                self.parent.title(f"Database Comparer: {self.controller.model.config['database']}")
                self.status_var.set("Settings updated and applied.")
                dialog.destroy()
                messagebox.showinfo("Settings", "Settings saved and applied successfully.")
                self.update_pagination()
                self.display_page()
            except Exception as e:
                messagebox.showerror("Error", f"Error saving settings: {str(e)}")
        ttk.Button(button_frame, text="Save", command=save_settings).pack(side="right", padx=5)
        ttk.Button(button_frame, text="Cancel", command=dialog.destroy).pack(side="right", padx=5)
    
    def show_about(self):
        dialog = tk.Toplevel(self.parent)
        dialog.title("About Database Comparer")
        dialog.geometry("400x300")
        dialog.minsize(300, 250)
        dialog.transient(self.parent)
        dialog.grab_set()
        ttk.Label(dialog, text="Database Comparer", font=("", 16, "bold")).pack(pady=(20, 5))
        ttk.Label(dialog, text=f"Version 2.0").pack(pady=5)
        ttk.Label(dialog, text="An optimized tool for comparing database states", wraplength=350).pack(pady=5)
        ttk.Separator(dialog).pack(fill="x", padx=20, pady=15)
        description = "This application allows you to compare two states of a database and identify changes between them. It is optimized for handling large databases efficiently."
        ttk.Label(dialog, text=description, wraplength=350, justify="center").pack(pady=5, padx=20)
        ttk.Button(dialog, text="Close", command=dialog.destroy).pack(pady=20)
    
    def set_buttons_state(self, state):
        self.fetch_state_button.config(state=state)
        self.compare_states_button.config(state=state)
        self.export_csv_button.config(state=state)
        self.clear_all_button.config(state=state)
    
    def _update_progress(self, status=None, current=0, total=1, sub_progress=None):
        if total == 0:
            progress = 100
        elif sub_progress is not None:
            progress = ((current + sub_progress) / total) * 100
        else:
            progress = (current / total) * 100
        self.parent.after(0, lambda: self.progress_var.set(progress))
        if status:
            self.parent.after(0, lambda: self.status_var.set(status))
    
    def _show_error(self, message):
        self.set_buttons_state("normal")
        self.status_var.set("Error")
        self.progress_var.set(0)
        messagebox.showerror("Error", message)
        self.is_operation_running = False
    
    def refresh_view(self):
        self.display_page()

class Application:
    def __init__(self, master=None):
        self.master = master or tk.Tk()
        self.master.title("Database Comparer")
        try:
            script_dir = os.path.dirname(os.path.abspath(__file__))
            icon_path = os.path.join(script_dir, "icon.ico")
            if os.path.exists(icon_path):
                self.master.iconbitmap(icon_path)
        except:
            pass
        self.master.minsize(900, 600)
        try:
            if os.path.exists('temp_geometry.txt'):
                with open('temp_geometry.txt', 'r') as f:
                    geometry = f.read().strip()
                    self.master.geometry(geometry)
                os.remove('temp_geometry.txt')
            else:
                screen_width = self.master.winfo_screenwidth()
                screen_height = self.master.winfo_screenheight()
                width = int(screen_width * 0.8)
                height = int(screen_height * 0.8)
                self.master.geometry(f"{width}x{height}+{int((screen_width-width)/2)}+{int((screen_height-height)/2)}")
        except:
            screen_width = self.master.winfo_screenwidth()
            screen_height = self.master.winfo_screenheight()
            width = int(screen_width * 0.8)
            height = int(screen_height * 0.8)
            self.master.geometry(f"{width}x{height}+{int((screen_width-width)/2)}+{int((screen_height-height)/2)}")
        self.show_splash()
        self.init_app()
    
    def show_splash(self):
        splash = tk.Toplevel(self.master)
        splash.overrideredirect(True)
        width, height = 400, 200
        x = (splash.winfo_screenwidth() - width) // 2
        y = (splash.winfo_screenheight() - height) // 2
        splash.geometry(f"{width}x{height}+{x}+{y}")
        frame = ttk.Frame(splash, relief="raised", borderwidth=2)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="Database Comparer", font=("", 16, "bold")).pack(pady=(40, 10))
        ttk.Label(frame, text="Initializing application...").pack(pady=10)
        progress = ttk.Progressbar(frame, mode="indeterminate")
        progress.pack(fill="x", padx=20, pady=20)
        progress.start()
        self.splash = splash
        self.master.update()
    
    def init_app(self):
        try:
            model = DatabaseModel()
            controller = DatabaseController(model)
            self.view = DatabaseCompareView(self.master, controller)
            self.master.after(1000, self.close_splash)
        except Exception as e:
            self.close_splash()
            messagebox.showerror("Initialization Error", f"Error initializing application:\n{str(e)}")
            self.master.destroy()
    
    def close_splash(self):
        if hasattr(self, 'splash'):
            self.splash.destroy()
            del self.splash
    
    def run(self):
        self.master.mainloop()

def create_config_if_missing():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    config_path = os.path.join(script_dir, 'config.ini')
    if not os.path.exists(config_path):
        config = configparser.ConfigParser()
        config['mysql'] = {
            'host': 'localhost',
            'database': 'test',
            'user': 'root',
            'password': '',
            'pool_size': '5'
        }
        with open(config_path, 'w') as configfile:
            config.write(configfile)
        return True
    return False

def handle_exception(exc_type, exc_value, exc_traceback):
    import traceback
    error_msg = ''.join(traceback.format_exception(exc_type, exc_value, exc_traceback))
    try:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        log_path = os.path.join(script_dir, 'error.log')
        with open(log_path, 'a') as log_file:
            log_file.write(f"\n--- {time.strftime('%Y-%m-%d %H:%M:%S')} ---\n")
            log_file.write(error_msg)
    except:
        pass
    messagebox.showerror("Application Error", f"An unexpected error occurred:\n\n{str(exc_value)}\n\nError details have been logged.")

if __name__ == "__main__":
    sys.excepthook = handle_exception
    if create_config_if_missing():
        messagebox.showinfo("First Run Setup", "A default configuration file has been created. Please update the database connection settings.")
    app = Application()
    app.run()
