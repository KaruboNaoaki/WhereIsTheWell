#!/usr/bin/env python3
"""
Where's the Well? - Water Source Locator
A desktop application for logging and tracking water sources in underserved communities
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import sqlite3
import os
import json
import random
from datetime import datetime
from PIL import Image, ImageTk
import folium
import webbrowser
import tempfile
from pathlib import Path

# Create data directory if it doesn't exist
DATA_DIR = Path("water_well_data")
DATA_DIR.mkdir(exist_ok=True)
IMAGES_DIR = DATA_DIR / "images"
IMAGES_DIR.mkdir(exist_ok=True)

class WaterSourceDatabase:
    """Handle all database operations"""
    
    def __init__(self):
        self.db_path = DATA_DIR / "water_sources.db"
        self.init_database()
    
    def init_database(self):
        """Initialize the SQLite database"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS water_sources (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                source_type TEXT NOT NULL,
                latitude REAL NOT NULL,
                longitude REAL NOT NULL,
                cleanliness TEXT NOT NULL,
                notes TEXT,
                image_path TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        conn.commit()
        conn.close()
    
    def add_source(self, name, source_type, lat, lon, cleanliness, notes, image_path):
        """Add a new water source"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO water_sources (name, source_type, latitude, longitude, cleanliness, notes, image_path)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (name, source_type, lat, lon, cleanliness, notes, image_path))
        
        conn.commit()
        conn.close()
    
    def get_all_sources(self):
        """Get all water sources"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('SELECT * FROM water_sources ORDER BY created_at DESC')
        sources = cursor.fetchall()
        
        conn.close()
        return sources
    
    def get_sources_by_cleanliness(self, cleanliness):
        """Get water sources filtered by cleanliness"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('SELECT * FROM water_sources WHERE cleanliness = ? ORDER BY created_at DESC', (cleanliness,))
        sources = cursor.fetchall()
        
        conn.close()
        return sources

class WaterAnalyzer:
    """Placeholder water analysis system"""
    
    @staticmethod
    def analyze_water(image_path):
        """
        Simulate water quality analysis
        In production, this would use a real ML model
        """
        # Placeholder: randomly assign cleanliness with weighted probabilities
        outcomes = ['Clean', 'Muddy', 'Contaminated']
        weights = [0.5, 0.3, 0.2]  # 50% clean, 30% muddy, 20% contaminated
        
        result = random.choices(outcomes, weights=weights)[0]
        
        # Simulate processing time
        import time
        time.sleep(0.5)
        
        return result

class WhereIsTheWellApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Where's the Well? - Water Source Locator")
        
        # Database
        self.db = WaterSourceDatabase()
        
        # Configure window
        self.setup_window()
        
        # Create UI
        self.create_widgets()
        
        # Load existing sources
        self.refresh_sources_list()
        
    def setup_window(self):
        """Configure window settings and responsiveness"""
        # Get screen dimensions
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        
        # Set window size (80% of screen)
        window_width = int(screen_width * 0.8)
        window_height = int(screen_height * 0.8)
        
        # Center window
        x = (screen_width - window_width) // 2
        y = (screen_height - window_height) // 2
        
        self.root.geometry(f"{window_width}x{window_height}+{x}+{y}")
        self.root.minsize(800, 600)
        
        # Configure grid weight for responsiveness
        self.root.grid_rowconfigure(0, weight=1)
        self.root.grid_columnconfigure(0, weight=1)
        
    def create_widgets(self):
        """Create all UI widgets"""
        # Main notebook for tabs
        self.notebook = ttk.Notebook(self.root)
        self.notebook.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)
        
        # Create tabs
        self.create_add_source_tab()
        self.create_view_sources_tab()
        self.create_map_tab()
        
    def create_add_source_tab(self):
        """Create the tab for adding new water sources"""
        add_frame = ttk.Frame(self.notebook)
        self.notebook.add(add_frame, text="Add Water Source")
        
        # Configure grid
        add_frame.grid_columnconfigure(1, weight=1)
        
        # Title
        title_label = ttk.Label(add_frame, text="Log New Water Source", font=("Arial", 16, "bold"))
        title_label.grid(row=0, column=0, columnspan=3, pady=20)
        
        # Source name
        ttk.Label(add_frame, text="Source Name:").grid(row=1, column=0, sticky="e", padx=10, pady=5)
        self.name_entry = ttk.Entry(add_frame, width=30)
        self.name_entry.grid(row=1, column=1, sticky="ew", padx=10, pady=5)
        
        # Source type
        ttk.Label(add_frame, text="Source Type:").grid(row=2, column=0, sticky="e", padx=10, pady=5)
        self.source_type = ttk.Combobox(add_frame, values=["Well", "River", "Spring", "Pond", "Tank", "Other"])
        self.source_type.grid(row=2, column=1, sticky="ew", padx=10, pady=5)
        self.source_type.current(0)
        
        # GPS Coordinates
        ttk.Label(add_frame, text="GPS Coordinates:").grid(row=3, column=0, sticky="ne", padx=10, pady=5)
        gps_frame = ttk.Frame(add_frame)
        gps_frame.grid(row=3, column=1, sticky="ew", padx=10, pady=5)
        
        ttk.Label(gps_frame, text="Latitude:").grid(row=0, column=0, padx=5)
        self.lat_entry = ttk.Entry(gps_frame, width=15)
        self.lat_entry.grid(row=0, column=1, padx=5)
        self.lat_entry.insert(0, "0.0")
        
        ttk.Label(gps_frame, text="Longitude:").grid(row=0, column=2, padx=5)
        self.lon_entry = ttk.Entry(gps_frame, width=15)
        self.lon_entry.grid(row=0, column=3, padx=5)
        self.lon_entry.insert(0, "0.0")
        
        # Notes
        ttk.Label(add_frame, text="Notes:").grid(row=4, column=0, sticky="ne", padx=10, pady=5)
        self.notes_text = tk.Text(add_frame, height=4, width=40)
        self.notes_text.grid(row=4, column=1, sticky="ew", padx=10, pady=5)
        
        # Image upload
        ttk.Label(add_frame, text="Water Image:").grid(row=5, column=0, sticky="ne", padx=10, pady=5)
        image_frame = ttk.Frame(add_frame)
        image_frame.grid(row=5, column=1, sticky="ew", padx=10, pady=5)
        
        self.image_path_var = tk.StringVar()
        self.image_label = ttk.Label(image_frame, text="No image selected")
        self.image_label.grid(row=0, column=0, padx=5)
        
        ttk.Button(image_frame, text="Upload Image", command=self.upload_image).grid(row=0, column=1, padx=5)
        
        # Image preview
        self.preview_label = ttk.Label(add_frame)
        self.preview_label.grid(row=6, column=1, pady=10)
        
        # Analysis result
        self.analysis_frame = ttk.LabelFrame(add_frame, text="Water Analysis Result", padding=10)
        self.analysis_frame.grid(row=7, column=0, columnspan=2, pady=20, padx=20, sticky="ew")
        self.analysis_label = ttk.Label(self.analysis_frame, text="Upload an image to analyze water quality", font=("Arial", 12))
        self.analysis_label.pack()
        
        # Submit button
        submit_btn = ttk.Button(add_frame, text="Save Water Source", command=self.save_water_source, style="Accent.TButton")
        submit_btn.grid(row=8, column=0, columnspan=2, pady=20)
        
    def create_view_sources_tab(self):
        """Create the tab for viewing water sources"""
        view_frame = ttk.Frame(self.notebook)
        self.notebook.add(view_frame, text="View Sources")
        
        # Configure grid
        view_frame.grid_columnconfigure(0, weight=1)
        view_frame.grid_rowconfigure(1, weight=1)
        
        # Title and filter
        header_frame = ttk.Frame(view_frame)
        header_frame.grid(row=0, column=0, sticky="ew", padx=10, pady=10)
        
        ttk.Label(header_frame, text="Water Sources", font=("Arial", 16, "bold")).pack(side="left", padx=10)
        
        # Filter by cleanliness
        ttk.Label(header_frame, text="Filter:").pack(side="left", padx=10)
        self.filter_var = tk.StringVar(value="All")
        filter_combo = ttk.Combobox(header_frame, textvariable=self.filter_var, 
                                   values=["All", "Clean", "Muddy", "Contaminated"], width=15)
        filter_combo.pack(side="left", padx=5)
        filter_combo.bind("<<ComboboxSelected>>", lambda e: self.refresh_sources_list())
        
        # Refresh button
        ttk.Button(header_frame, text="Refresh", command=self.refresh_sources_list).pack(side="left", padx=20)
        
        # Sources list
        list_frame = ttk.Frame(view_frame)
        list_frame.grid(row=1, column=0, sticky="nsew", padx=10, pady=10)
        list_frame.grid_columnconfigure(0, weight=1)
        list_frame.grid_rowconfigure(0, weight=1)
        
        # Treeview with scrollbar
        self.sources_tree = ttk.Treeview(list_frame, columns=("Type", "Cleanliness", "Lat", "Lon", "Date"), show="tree headings")
        self.sources_tree.grid(row=0, column=0, sticky="nsew")
        
        # Configure columns
        self.sources_tree.heading("#0", text="Name")
        self.sources_tree.heading("Type", text="Type")
        self.sources_tree.heading("Cleanliness", text="Water Quality")
        self.sources_tree.heading("Lat", text="Latitude")
        self.sources_tree.heading("Lon", text="Longitude")
        self.sources_tree.heading("Date", text="Date Added")
        
        # Column widths
        self.sources_tree.column("#0", width=200)
        self.sources_tree.column("Type", width=100)
        self.sources_tree.column("Cleanliness", width=120)
        self.sources_tree.column("Lat", width=100)
        self.sources_tree.column("Lon", width=100)
        self.sources_tree.column("Date", width=150)
        
        # Scrollbar
        scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=self.sources_tree.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.sources_tree.configure(yscrollcommand=scrollbar.set)
        
        # Stats frame
        stats_frame = ttk.LabelFrame(view_frame, text="Statistics", padding=10)
        stats_frame.grid(row=2, column=0, sticky="ew", padx=10, pady=10)
        
        self.stats_label = ttk.Label(stats_frame, text="", font=("Arial", 11))
        self.stats_label.pack()
        
    def create_map_tab(self):
        """Create the map tab"""
        map_frame = ttk.Frame(self.notebook)
        self.notebook.add(map_frame, text="Map View")
        
        # Configure grid
        map_frame.grid_columnconfigure(0, weight=1)
        map_frame.grid_rowconfigure(1, weight=1)
        
        # Header
        header_frame = ttk.Frame(map_frame)
        header_frame.grid(row=0, column=0, sticky="ew", padx=10, pady=10)
        
        ttk.Label(header_frame, text="Water Sources Map", font=("Arial", 16, "bold")).pack(side="left", padx=10)
        ttk.Button(header_frame, text="Generate Map", command=self.generate_map).pack(side="left", padx=20)
        ttk.Button(header_frame, text="Open in Browser", command=self.open_map_browser).pack(side="left", padx=5)
        
        # Map display area
        self.map_frame = ttk.Frame(map_frame, relief="sunken", borderwidth=2)
        self.map_frame.grid(row=1, column=0, sticky="nsew", padx=10, pady=10)
        
        # Map info
        info_label = ttk.Label(self.map_frame, text="Click 'Generate Map' to create an interactive map of water sources", 
                              font=("Arial", 12))
        info_label.place(relx=0.5, rely=0.5, anchor="center")
        
    def upload_image(self):
        """Handle image upload"""
        filename = filedialog.askopenfilename(
            title="Select Water Image",
            filetypes=[("Image files", "*.jpg *.jpeg *.png *.gif *.bmp"), ("All files", "*.*")]
        )
        
        if filename:
            self.image_path_var.set(filename)
            self.image_label.config(text=os.path.basename(filename))
            
            # Show preview
            self.show_image_preview(filename)
            
            # Analyze water (placeholder)
            self.analyze_water_image(filename)
    
    def show_image_preview(self, image_path):
        """Show a preview of the uploaded image"""
        try:
            # Open and resize image
            image = Image.open(image_path)
            image.thumbnail((200, 150), Image.Resampling.LANCZOS)
            
            # Convert to PhotoImage
            photo = ImageTk.PhotoImage(image)
            
            # Update preview
            self.preview_label.config(image=photo)
            self.preview_label.image = photo  # Keep reference
        except Exception as e:
            print(f"Error showing preview: {e}")
    
    def analyze_water_image(self, image_path):
        """Analyze water quality from image"""
        self.analysis_label.config(text="Analyzing water quality...", foreground="blue")
        self.root.update()
        
        # Run placeholder analysis
        result = WaterAnalyzer.analyze_water(image_path)
        
        # Update UI with result
        color_map = {
            "Clean": "green",
            "Muddy": "orange",
            "Contaminated": "red"
        }
        
        self.analysis_label.config(
            text=f"Water Quality: {result}",
            foreground=color_map.get(result, "black"),
            font=("Arial", 14, "bold")
        )
        
        # Store result
        self.water_quality = result
    
    def save_water_source(self):
        """Save a new water source to database"""
        # Validate inputs
        name = self.name_entry.get().strip()
        if not name:
            messagebox.showerror("Error", "Please enter a source name")
            return
        
        try:
            lat = float(self.lat_entry.get())
            lon = float(self.lon_entry.get())
        except ValueError:
            messagebox.showerror("Error", "Please enter valid GPS coordinates")
            return
        
        if not hasattr(self, 'water_quality'):
            messagebox.showerror("Error", "Please upload and analyze a water image")
            return
        
        # Save image
        image_filename = None
        if self.image_path_var.get():
            # Copy image to data directory
            source_path = self.image_path_var.get()
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            ext = os.path.splitext(source_path)[1]
            image_filename = f"{timestamp}_{name.replace(' ', '_')}{ext}"
            dest_path = IMAGES_DIR / image_filename
            
            try:
                Image.open(source_path).save(dest_path)
            except Exception as e:
                print(f"Error saving image: {e}")
        
        # Get other values
        source_type = self.source_type.get()
        notes = self.notes_text.get("1.0", "end-1c").strip()
        
        # Save to database
        self.db.add_source(name, source_type, lat, lon, self.water_quality, notes, str(image_filename))
        
        # Clear form
        self.clear_form()
        
        # Refresh list
        self.refresh_sources_list()
        
        # Show success
        messagebox.showinfo("Success", "Water source saved successfully!")
        
        # Switch to view tab
        self.notebook.select(1)
    
    def clear_form(self):
        """Clear the add source form"""
        self.name_entry.delete(0, tk.END)
        self.lat_entry.delete(0, tk.END)
        self.lat_entry.insert(0, "0.0")
        self.lon_entry.delete(0, tk.END)
        self.lon_entry.insert(0, "0.0")
        self.notes_text.delete("1.0", tk.END)
        self.image_path_var.set("")
        self.image_label.config(text="No image selected")
        self.preview_label.config(image="")
        self.analysis_label.config(text="Upload an image to analyze water quality", foreground="black")
        if hasattr(self, 'water_quality'):
            del self.water_quality
    
    def refresh_sources_list(self):
        """Refresh the water sources list"""
        # Clear existing items
        for item in self.sources_tree.get_children():
            self.sources_tree.delete(item)
        
        # Get sources
        filter_value = self.filter_var.get()
        if filter_value == "All":
            sources = self.db.get_all_sources()
        else:
            sources = self.db.get_sources_by_cleanliness(filter_value)
        
        # Add to tree
        for source in sources:
            # Format date
            date_str = source[8][:10] if source[8] else ""
            
            # Add tags for coloring
            tags = (source[5].lower(),)  # cleanliness as tag
            
            self.sources_tree.insert("", "end", text=source[1], 
                                   values=(source[2], source[5], f"{source[3]:.6f}", 
                                          f"{source[4]:.6f}", date_str),
                                   tags=tags)
        
        # Configure tag colors
        self.sources_tree.tag_configure("clean", foreground="green")
        self.sources_tree.tag_configure("muddy", foreground="orange")
        self.sources_tree.tag_configure("contaminated", foreground="red")
        
        # Update statistics
        self.update_statistics()
    
    def update_statistics(self):
        """Update statistics display"""
        all_sources = self.db.get_all_sources()
        total = len(all_sources)
        
        if total == 0:
            self.stats_label.config(text="No water sources logged yet")
            return
        
        # Count by cleanliness
        clean = len([s for s in all_sources if s[5] == "Clean"])
        muddy = len([s for s in all_sources if s[5] == "Muddy"])
        contaminated = len([s for s in all_sources if s[5] == "Contaminated"])
        
        stats_text = f"Total Sources: {total}  |  Clean: {clean} ({clean/total*100:.1f}%)  |  " \
                    f"Muddy: {muddy} ({muddy/total*100:.1f}%)  |  " \
                    f"Contaminated: {contaminated} ({contaminated/total*100:.1f}%)"
        
        self.stats_label.config(text=stats_text)
    
    def generate_map(self):
        """Generate an interactive map"""
        sources = self.db.get_all_sources()
        
        if not sources:
            messagebox.showinfo("Info", "No water sources to display on map")
            return
        
        # Calculate center (average of all coordinates)
        avg_lat = sum(s[3] for s in sources) / len(sources)
        avg_lon = sum(s[4] for s in sources) / len(sources)
        
        # Create map
        m = folium.Map(location=[avg_lat, avg_lon], zoom_start=10)
        
        # Color mapping
        color_map = {
            "Clean": "green",
            "Muddy": "orange",
            "Contaminated": "red"
        }
        
        # Add markers
        for source in sources:
            popup_text = f"""
            <b>{source[1]}</b><br>
            Type: {source[2]}<br>
            Quality: {source[5]}<br>
            Notes: {source[6] or 'N/A'}<br>
            Added: {source[8][:10]}
            """
            
            folium.Marker(
                [source[3], source[4]],
                popup=popup_text,
                tooltip=f"{source[1]} - {source[5]}",
                icon=folium.Icon(color=color_map.get(source[5], "blue"))
            ).add_to(m)
        
        # Save map
        self.map_path = DATA_DIR / "water_sources_map.html"
        m.save(str(self.map_path))
        
        # Update UI
        info_text = f"Map generated with {len(sources)} water sources.\nClick 'Open in Browser' to view the interactive map."
        
        # Clear existing widgets in map frame
        for widget in self.map_frame.winfo_children():
            widget.destroy()
        
        # Show info
        info_label = ttk.Label(self.map_frame, text=info_text, font=("Arial", 12))
        info_label.place(relx=0.5, rely=0.5, anchor="center")
        
        messagebox.showinfo("Success", "Map generated successfully!")
    
    def open_map_browser(self):
        """Open the generated map in browser"""
        if hasattr(self, 'map_path') and os.path.exists(self.map_path):
            webbrowser.open(f"file://{self.map_path}")
        else:
            messagebox.showinfo("Info", "Please generate a map first")

def main():
    """Main application entry point"""
    root = tk.Tk()
    
    # Style
    style = ttk.Style()
    style.theme_use('clam')
    
    # Configure accent button style
    style.configure("Accent.TButton", foreground="white", background="#007ACC")
    style.map("Accent.TButton", background=[('active', '#005A9E')])
    
    # Create application
    app = WhereIsTheWellApp(root)
    
    # Run
    root.mainloop()

if __name__ == "__main__":
    main()
