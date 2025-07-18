import os
import sqlite3
import base64
import json
from datetime import datetime
from flask import Flask, render_template_string, request, jsonify, send_from_directory
import cv2
import numpy as np
from PIL import Image
import io

app = Flask(__name__)

# Database setup
def init_db():
    conn = sqlite3.connect('water_sources.db')
    cursor = conn.cursor()
    
    # Water sources table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS water_sources (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            latitude REAL NOT NULL,
            longitude REAL NOT NULL,
            water_type TEXT,
            cleanliness_level TEXT,
            confidence_score REAL,
            notes TEXT,
            photo_data TEXT,
            added_by TEXT DEFAULT 'Anonymous',
            admin_override TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Check if added_by column exists, add it if not
    cursor.execute("PRAGMA table_info(water_sources)")
    columns = [column[1] for column in cursor.fetchall()]
    if 'added_by' not in columns:
        cursor.execute('ALTER TABLE water_sources ADD COLUMN added_by TEXT DEFAULT "Anonymous"')
    if 'admin_override' not in columns:
        cursor.execute('ALTER TABLE water_sources ADD COLUMN admin_override TEXT')
    
    # Votes table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS votes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            water_source_id INTEGER,
            username TEXT NOT NULL,
            vote_type TEXT CHECK(vote_type IN ('upvote', 'downvote')),
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (water_source_id) REFERENCES water_sources (id),
            UNIQUE(water_source_id, username)
        )
    ''')
    
    # Comments table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS comments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            water_source_id INTEGER,
            username TEXT NOT NULL,
            comment TEXT NOT NULL,
            is_admin BOOLEAN DEFAULT FALSE,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (water_source_id) REFERENCES water_sources (id)
        )
    ''')
    
    # Check if is_admin column exists in comments, add it if not
    cursor.execute("PRAGMA table_info(comments)")
    comment_columns = [column[1] for column in cursor.fetchall()]
    if 'is_admin' not in comment_columns:
        cursor.execute('ALTER TABLE comments ADD COLUMN is_admin BOOLEAN DEFAULT FALSE')
    
    # Alerts table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            message TEXT NOT NULL,
            latitude REAL NOT NULL,
            longitude REAL NOT NULL,
            alert_type TEXT DEFAULT 'warning',
            added_by TEXT NOT NULL,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    conn.commit()
    conn.close()

# Simple water quality classifier using OpenCV heuristics
class WaterQualityClassifier:
    def __init__(self):
        pass
    
    def analyze_water_image(self, image_data):
        """
        Analyze water quality based on color, turbidity, and visual characteristics
        Returns: (cleanliness_level, confidence_score)
        """
        try:
            # Decode base64 image
            image_bytes = base64.b64decode(image_data.split(',')[1])
            image = Image.open(io.BytesIO(image_bytes))
            img_array = np.array(image)
            
            # Convert to different color spaces for analysis
            hsv = cv2.cvtColor(img_array, cv2.COLOR_RGB2HSV)
            gray = cv2.cvtColor(img_array, cv2.COLOR_RGB2GRAY)
            
            # Calculate various metrics
            brightness = np.mean(gray)
            contrast = np.std(gray)
            
            # Analyze color distribution
            blue_channel = img_array[:, :, 2]
            green_channel = img_array[:, :, 1]
            red_channel = img_array[:, :, 0]
            
            blue_mean = np.mean(blue_channel)
            green_mean = np.mean(green_channel)
            red_mean = np.mean(red_channel)
            
            # Calculate turbidity indicator (standard deviation of brightness)
            turbidity = np.std(gray)
            
            # Color analysis for contamination
            brown_pixels = np.sum((red_channel > 100) & (green_channel > 80) & (blue_channel < 80))
            total_pixels = img_array.shape[0] * img_array.shape[1]
            brown_ratio = brown_pixels / total_pixels
            
            # Classification logic
            confidence = 0.7  # Base confidence
            
            # Clean water indicators
            if (blue_mean > green_mean and blue_mean > red_mean and 
                turbidity < 30 and brown_ratio < 0.1 and brightness > 100):
                return "clean", min(0.95, confidence + 0.2)
            
            # Muddy water indicators
            elif (brown_ratio > 0.15 or turbidity > 50 or 
                  (red_mean > blue_mean and green_mean > blue_mean)):
                return "muddy", min(0.9, confidence + 0.1)
            
            # Contaminated water indicators
            elif (turbidity > 40 or brightness < 50 or 
                  abs(red_mean - green_mean) > 50):
                return "contaminated", min(0.85, confidence + 0.05)
            
            # Default to muddy if uncertain
            else:
                return "muddy", confidence - 0.2
                
        except Exception as e:
            print(f"Error analyzing image: {e}")
            return "unknown", 0.3

classifier = WaterQualityClassifier()

# HTML Template with Tailwind CSS and Interactive Map
HTML_TEMPLATE = '''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Where's the Well? - Water Source Locator</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
    <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
    <style>
        .water-marker-clean { background-color: #10b981; }
        .water-marker-muddy { background-color: #f59e0b; }
        .water-marker-contaminated { background-color: #ef4444; }
        .user-location { background-color: #3b82f6; }
        
        .wave-background {
            background: linear-gradient(-45deg, #1e3a8a, #3b82f6, #60a5fa, #93c5fd);
            background-size: 400% 400%;
            animation: gradientWave 12s ease infinite;
            position: relative;
            overflow: hidden;
        }
        
        .wave-background::before {
            content: '';
            position: absolute;
            top: 0;
            left: 0;
            right: 0;
            bottom: 0;
            background: 
                radial-gradient(circle at 20% 80%, rgba(255,255,255,0.1) 0%, transparent 50%),
                radial-gradient(circle at 80% 20%, rgba(255,255,255,0.1) 0%, transparent 50%),
                radial-gradient(circle at 40% 40%, rgba(255,255,255,0.05) 0%, transparent 50%);
            animation: waveFloat 8s ease-in-out infinite;
        }
        
        @keyframes gradientWave {
            0% {
                background-position: 0% 50%;
            }
            50% {
                background-position: 100% 50%;
            }
            100% {
                background-position: 0% 50%;
            }
        }
        
        @keyframes waveFloat {
            0%, 100% {
                transform: translate(0, 0) scale(1);
            }
            33% {
                transform: translate(20px, -20px) scale(1.1);
            }
            66% {
                transform: translate(-20px, 20px) scale(0.9);
            }
        }
    </style>
</head>
<body class="bg-gray-100 min-h-screen">
    <!-- Login Page -->
    <div id="loginPage" class="fixed inset-0 wave-background flex items-center justify-center z-50">
        <div class="w-full h-full flex items-center justify-center p-4">
            <div class="bg-white rounded-2xl shadow-2xl p-12 max-w-md w-full relative z-10">
                <div class="text-center mb-8">
                    <div class="mb-6">
                        <svg class="w-16 h-16 mx-auto text-blue-600" fill="currentColor" viewBox="0 0 20 20">
                            <path fill-rule="evenodd" d="M5.05 4.05a7 7 0 119.9 9.9L10 18.9l-4.95-4.95a7 7 0 010-9.9zM10 11a2 2 0 100-4 2 2 0 000 4z" clip-rule="evenodd"></path>
                        </svg>
                    </div>
                    <h1 class="text-3xl font-bold text-gray-800 mb-3">Where's the Well?</h1>
                    <p class="text-gray-600 mb-8">Access the Interactive Water Source Locator</p>
                </div>
                
                <form id="loginForm" class="space-y-6">
                    <div>
                        <label class="block text-sm font-medium text-gray-700 mb-2">Username</label>
                        <input type="text" id="usernameInput" class="w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition" placeholder="Enter your username" required>
                    </div>
                    
                    <div>
                        <label class="block text-sm font-medium text-gray-700 mb-2">Password</label>
                        <input type="password" id="passwordInput" class="w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition" placeholder="Enter your password" required>
                    </div>
                    
                    <button type="submit" class="w-full bg-blue-600 text-white py-3 px-4 rounded-lg hover:bg-blue-700 transition font-medium text-lg">
                        🚀 Sign In
                    </button>
                </form>
            </div>
        </div>
    </div>

    <!-- Header -->
    <header class="bg-blue-600 text-white shadow-lg">
        <div class="container mx-auto px-4 py-6">
            <div class="flex justify-between items-center">
                <div>
                    <h1 class="text-3xl font-bold flex items-center">
                        <svg class="w-8 h-8 mr-3" fill="currentColor" viewBox="0 0 20 20">
                            <path fill-rule="evenodd" d="M5.05 4.05a7 7 0 119.9 9.9L10 18.9l-4.95-4.95a7 7 0 010-9.9zM10 11a2 2 0 100-4 2 2 0 000 4z" clip-rule="evenodd"></path>
                        </svg>
                        Where's the Well?
                    </h1>
                    <p class="text-blue-100 mt-2">Interactive Water Source Locator</p>
                </div>
                <div class="text-right">
                    <p class="text-blue-100">Welcome, <span id="currentUsername" class="font-semibold"></span>!</p>
                    <button onclick="logout()" class="text-blue-200 hover:text-white text-sm underline">Change User</button>
                </div>
            </div>
        </div>
    </header>

    <!-- Main Content -->
    <div id="mainContent" class="container mx-auto px-4 py-8" style="display: none;">
        <div class="grid grid-cols-1 lg:grid-cols-3 gap-8">
            
            <!-- Map Column -->
            <div class="lg:col-span-2 space-y-6">
                <div class="bg-white rounded-xl shadow-lg overflow-hidden">
                    <div class="p-6 border-b border-gray-200">
                        <h2 class="text-xl font-semibold text-gray-800 flex items-center">
                            <svg class="w-5 h-5 mr-2" fill="currentColor" viewBox="0 0 20 20">
                                <path fill-rule="evenodd" d="M12 1.586l-4 4v12.828l4-4V1.586zM3.707 3.293A1 1 0 002 4v10a1 1 0 00.293.707L6 18.414V5.586L3.707 3.293zM17.707 5.293L14 1.586v12.828l3.707 3.707A1 1 0 0018 18V8a1 1 0 00-.293-.707z" clip-rule="evenodd"></path>
                            </svg>
                            Interactive Map
                        </h2>
                        <p class="text-gray-600 text-sm mt-1">Click on the map to add a new water source, or click a marker for details</p>
                    </div>
                    <div id="map" class="h-96 w-full"></div>
                    <div class="p-4 bg-gray-50">
                        <div class="flex items-center justify-between text-sm">
                            <div class="flex items-center space-x-4">
                                <div class="flex items-center">
                                    <div class="w-3 h-3 bg-green-500 rounded-full mr-2"></div>
                                    <span>Clean Water</span>
                                </div>
                                <div class="flex items-center">
                                    <div class="w-3 h-3 bg-yellow-500 rounded-full mr-2"></div>
                                    <span>Muddy Water</span>
                                </div>
                                <div class="flex items-center">
                                    <div class="w-3 h-3 bg-red-500 rounded-full mr-2"></div>
                                    <span>Contaminated</span>
                                </div>
                                <div class="flex items-center">
                                    <div class="w-3 h-3 bg-blue-500 rounded-full mr-2"></div>
                                    <span>Your Location</span>
                                </div>
                            </div>
                            <button onclick="getCurrentLocation()" class="px-3 py-1 bg-blue-500 text-white rounded hover:bg-blue-600 transition">
                                📍 Find Me
                            </button>
                        </div>
                    </div>
                </div>

                <!-- Water Source Details Panel -->
                <div id="detailsPanel" class="bg-white rounded-xl shadow-lg overflow-hidden hidden">
                    <div class="p-6 border-b border-gray-200">
                        <h3 class="text-xl font-semibold text-gray-800">Water Source Details</h3>
                    </div>
                    <div id="detailsContent" class="p-6">
                        <!-- Details content will be populated here -->
                    </div>
                </div>
            </div>

            <!-- Control Panel Column -->
            <div class="space-y-6">
                
                <!-- Add Water Source Form -->
                <div class="bg-white rounded-xl shadow-lg p-6">
                    <h3 class="text-lg font-semibold text-gray-800 mb-4">Add Water Source</h3>
                    <form id="waterSourceForm" class="space-y-4">
                        <div>
                            <label class="block text-sm font-medium text-gray-700 mb-2">Source Name</label>
                            <input type="text" id="sourceName" class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500" placeholder="e.g., Village Well #1" required>
                        </div>
                        
                        <div>
                            <label class="block text-sm font-medium text-gray-700 mb-2">Water Type</label>
                            <select id="waterType" class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500">
                                <option value="well">Well</option>
                                <option value="spring">Spring</option>
                                <option value="river">River</option>
                                <option value="lake">Lake</option>
                                <option value="pond">Pond</option>
                                <option value="other">Other</option>
                            </select>
                        </div>

                        <div>
                            <label class="block text-sm font-medium text-gray-700 mb-2">Location</label>
                            <div class="grid grid-cols-2 gap-2">
                                <input type="number" id="latitude" step="any" class="px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500" placeholder="Latitude" readonly>
                                <input type="number" id="longitude" step="any" class="px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500" placeholder="Longitude" readonly>
                            </div>
                            <p class="text-xs text-gray-500 mt-1">Click on map to set location</p>
                        </div>

                        <div>
                            <label class="block text-sm font-medium text-gray-700 mb-2">Water Photo</label>
                            <div class="border-2 border-dashed border-gray-300 rounded-lg p-4 text-center hover:border-blue-400 transition">
                                <input type="file" id="photoInput" accept="image/*" class="hidden" onchange="handlePhotoUpload(event)">
                                <button type="button" onclick="document.getElementById('photoInput').click()" class="text-blue-600 hover:text-blue-800">
                                    📷 Upload Photo or Take Picture
                                </button>
                                <div id="photoPreview" class="mt-2 hidden">
                                    <img id="previewImage" class="max-w-full h-32 object-cover rounded-lg mx-auto">
                                    <div id="analysisResult" class="mt-2 p-2 rounded text-sm"></div>
                                </div>
                            </div>
                        </div>

                        <div>
                            <label class="block text-sm font-medium text-gray-700 mb-2">Notes</label>
                            <textarea id="notes" rows="3" class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500" placeholder="Additional observations..."></textarea>
                        </div>

                        <button type="submit" class="w-full bg-blue-600 text-white py-2 px-4 rounded-lg hover:bg-blue-700 transition font-medium">
                            💧 Add Water Source
                        </button>
                    </form>
                </div>

                <!-- Water Sources Near Me -->
                <div class="bg-white rounded-xl shadow-lg p-6">
                    <h3 class="text-lg font-semibold text-gray-800 mb-4 flex items-center">
                        <svg class="w-5 h-5 mr-2" fill="currentColor" viewBox="0 0 20 20">
                            <path fill-rule="evenodd" d="M5.05 4.05a7 7 0 119.9 9.9L10 18.9l-4.95-4.95a7 7 0 010-9.9zM10 11a2 2 0 100-4 2 2 0 000 4z" clip-rule="evenodd"></path>
                        </svg>
                        Water Sources Near Me
                    </h3>
                    <div id="nearbySourcesContainer" class="space-y-3">
                        <div class="text-center py-8 text-gray-500">
                            <svg class="w-12 h-12 mx-auto mb-3 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M17.657 16.657L13.414 20.9a1.998 1.998 0 01-2.827 0l-4.244-4.243a8 8 0 1111.314 0z"></path>
                                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 11a3 3 0 11-6 0 3 3 0 016 0z"></path>
                            </svg>
                            <p>Click "Find Me" to see nearby water sources</p>
                        </div>
                    </div>
                </div>

                <!-- Alerts Near Me (Admin Only) -->
                <div id="alertsSection" class="bg-white rounded-xl shadow-lg p-6" style="display: none;">
                    <h3 class="text-lg font-semibold text-gray-800 mb-4 flex items-center">
                        <svg class="w-5 h-5 mr-2 text-red-500" fill="currentColor" viewBox="0 0 20 20">
                            <path fill-rule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clip-rule="evenodd"></path>
                        </svg>
                        Alerts Near Me
                        <span class="ml-2 px-2 py-1 bg-red-100 text-red-800 text-xs rounded-full">ADMIN</span>
                    </h3>
                    
                    <!-- Add Alert Form -->
                    <div class="mb-4 p-3 bg-red-50 rounded-lg">
                        <h4 class="font-medium text-gray-800 mb-2">Add New Alert</h4>
                        <form id="alertForm" class="space-y-2">
                            <input type="text" id="alertTitle" placeholder="Alert title..." class="w-full px-3 py-2 text-sm border border-gray-300 rounded-lg focus:ring-2 focus:ring-red-500 focus:border-red-500" required>
                            <textarea id="alertMessage" placeholder="Alert message..." rows="2" class="w-full px-3 py-2 text-sm border border-gray-300 rounded-lg focus:ring-2 focus:ring-red-500 focus:border-red-500 resize-none" required></textarea>
                            <input type="hidden" id="alertLatitude">
                            <input type="hidden" id="alertLongitude">
                            <button type="submit" class="w-full py-2 px-4 bg-red-600 text-white rounded-lg hover:bg-red-700 transition font-medium text-sm">
                                🚨 Add Alert to Map
                            </button>
                        </form>
                        <p class="text-xs text-gray-500 mt-2">Click on the map to set alert location</p>
                    </div>
                    
                    <div id="alertsContainer" class="space-y-3">
                        <div class="text-center py-4 text-gray-500">
                            <p class="text-sm">No alerts in your area</p>
                        </div>
                    </div>
                </div>

            </div>
        </div>
    </div>

    <script>
        // Global variables
        let map;
        let userLocationMarker;
        let waterSourceMarkers = [];
        let alertMarkers = [];
        let selectedLatLng = null;
        let currentPhotoData = null;
        let currentUsername = null;
        let userLocation = null;
        let isAdmin = false;
        let alertMode = false;

        // Initialize app when page loads
        document.addEventListener('DOMContentLoaded', function() {
            checkLogin();
        });

        // Check if user is logged in
        function checkLogin() {
            currentUsername = localStorage.getItem('wheres_the_well_username');
            if (currentUsername) {
                isAdmin = currentUsername.toLowerCase() === 'admin';
                document.getElementById('currentUsername').textContent = currentUsername + (isAdmin ? ' (Admin)' : '');
                document.getElementById('loginPage').style.display = 'none';
                document.getElementById('mainContent').style.display = 'block';
                
                // Show admin sections if admin
                if (isAdmin) {
                    document.getElementById('alertsSection').style.display = 'block';
                }
                
                initMap();
            } else {
                document.getElementById('loginPage').style.display = 'block';
                document.getElementById('mainContent').style.display = 'none';
            }
        }

        // Handle login
        document.getElementById('loginForm').addEventListener('submit', function(e) {
            e.preventDefault();
            const username = document.getElementById('usernameInput').value.trim();
            const password = document.getElementById('passwordInput').value; // Password is ignored but required for form
            
            if (username && password) {
                currentUsername = username;
                isAdmin = username.toLowerCase() === 'admin';
                localStorage.setItem('wheres_the_well_username', username);
                document.getElementById('currentUsername').textContent = username + (isAdmin ? ' (Admin)' : '');
                document.getElementById('loginPage').style.display = 'none';
                document.getElementById('mainContent').style.display = 'block';
                
                // Show admin sections if admin
                if (isAdmin) {
                    document.getElementById('alertsSection').style.display = 'block';
                }
                
                initMap();
            } else {
                alert('Please enter both username and password');
            }
        });

        // Logout function
        function logout() {
            // Clear user data
            localStorage.removeItem('wheres_the_well_username');
            currentUsername = null;
            userLocation = null;
            isAdmin = false;
            alertMode = false;
            
            // Clean up map and markers
            if (map) {
                // Remove all markers
                if (userLocationMarker) {
                    map.removeLayer(userLocationMarker);
                    userLocationMarker = null;
                }
                
                if (window.tempMarker) {
                    map.removeLayer(window.tempMarker);
                    window.tempMarker = null;
                }
                
                waterSourceMarkers.forEach(marker => map.removeLayer(marker));
                waterSourceMarkers = [];
                
                alertMarkers.forEach(marker => map.removeLayer(marker));
                alertMarkers = [];
                
                // Remove the map completely
                map.remove();
                map = null;
            }
            
            // Reset global variables
            selectedLatLng = null;
            currentPhotoData = null;
            
            // Hide main content and admin sections
            document.getElementById('mainContent').style.display = 'none';
            document.getElementById('alertsSection').style.display = 'none';
            document.getElementById('detailsPanel').classList.add('hidden');
            
            // Reset containers
            document.getElementById('nearbySourcesContainer').innerHTML = `
                <div class="text-center py-8 text-gray-500">
                    <svg class="w-12 h-12 mx-auto mb-3 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M17.657 16.657L13.414 20.9a1.998 1.998 0 01-2.827 0l-4.244-4.243a8 8 0 1111.314 0z"></path>
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 11a3 3 0 11-6 0 3 3 0 016 0z"></path>
                    </svg>
                    <p>Click "Find Me" to see nearby water sources</p>
                </div>
            `;
            
            document.getElementById('alertsContainer').innerHTML = `
                <div class="text-center py-4 text-gray-500">
                    <p class="text-sm">No alerts in your area</p>
                </div>
            `;
            
            // Reset forms
            document.getElementById('waterSourceForm').reset();
            document.getElementById('photoPreview').classList.add('hidden');
            document.getElementById('latitude').value = '';
            document.getElementById('longitude').value = '';
            
            // Show login page
            document.getElementById('loginPage').style.display = 'block';
            document.getElementById('usernameInput').value = '';
            document.getElementById('passwordInput').value = '';
        }

        // Initialize map
        function initMap() {
            // Default location (can be changed)
            const defaultLat = 40.7128;
            const defaultLng = -74.0060;
            
            map = L.map('map').setView([defaultLat, defaultLng], 13);
            
            // Add OpenStreetMap tiles
            L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
                attribution: '© OpenStreetMap contributors'
            }).addTo(map);

            // Add click event for placing water sources or alerts
            map.on('click', function(e) {
                if (isAdmin && alertMode) {
                    // Admin placing an alert
                    document.getElementById('alertLatitude').value = e.latlng.lat.toFixed(6);
                    document.getElementById('alertLongitude').value = e.latlng.lng.toFixed(6);
                    
                    // Show temporary alert marker
                    if (window.tempAlertMarker) {
                        map.removeLayer(window.tempAlertMarker);
                    }
                    window.tempAlertMarker = L.marker([e.latlng.lat, e.latlng.lng], {
                        icon: L.divIcon({
                            className: 'alert-marker',
                            html: '<div style="background-color: #ef4444; color: white; width: 30px; height: 30px; border-radius: 50%; display: flex; align-items: center; justify-content: center; border: 2px solid white; box-shadow: 0 2px 4px rgba(0,0,0,0.2); font-size: 16px;">🚨</div>',
                            iconSize: [30, 30],
                            iconAnchor: [15, 15]
                        })
                    }).addTo(map).bindPopup("📍 New alert location").openPopup();
                } else {
                    // Regular water source placement
                    selectedLatLng = e.latlng;
                    document.getElementById('latitude').value = e.latlng.lat.toFixed(6);
                    document.getElementById('longitude').value = e.latlng.lng.toFixed(6);
                    
                    // Show temporary marker
                    if (window.tempMarker) {
                        map.removeLayer(window.tempMarker);
                    }
                    window.tempMarker = L.marker([e.latlng.lat, e.latlng.lng])
                        .addTo(map)
                        .bindPopup("📍 New water source location")
                        .openPopup();
                }
            });

            // Try to get user's current location
            getCurrentLocation();
            
            // Load existing water sources
            loadWaterSources();
        }

        // Get current location
        function getCurrentLocation() {
            if (navigator.geolocation) {
                navigator.geolocation.getCurrentPosition(
                    function(position) {
                        const lat = position.coords.latitude;
                        const lng = position.coords.longitude;
                        
                        // Store user location
                        userLocation = { latitude: lat, longitude: lng };
                        
                        // Update map view
                        map.setView([lat, lng], 15);
                        
                        // Add/update user location marker
                        if (userLocationMarker) {
                            map.removeLayer(userLocationMarker);
                        }
                        
                        userLocationMarker = L.marker([lat, lng], {
                            icon: L.divIcon({
                                className: 'user-location',
                                html: '<div style="background-color: #3b82f6; width: 15px; height: 15px; border-radius: 50%; border: 3px solid white; box-shadow: 0 2px 4px rgba(0,0,0,0.2);"></div>',
                                iconSize: [21, 21],
                                iconAnchor: [10, 10]
                            })
                        }).addTo(map).bindPopup("📍 Your current location");
                        
                        // Update nearby sources list
                        updateNearbyWaterSources();
                        
                        // Update alerts if admin
                        if (isAdmin) {
                            updateAlertsNearMe();
                        }
                    },
                    function(error) {
                        console.log("Geolocation error:", error);
                        // Use default location if geolocation fails
                        userLocation = null;
                    }
                );
            }
        }

        // Handle photo upload and analysis
        function handlePhotoUpload(event) {
            const file = event.target.files[0];
            if (file) {
                const reader = new FileReader();
                reader.onload = function(e) {
                    currentPhotoData = e.target.result;
                    
                    // Show preview
                    const preview = document.getElementById('photoPreview');
                    const previewImage = document.getElementById('previewImage');
                    previewImage.src = currentPhotoData;
                    preview.classList.remove('hidden');
                    
                    // Analyze water quality
                    analyzeWaterQuality(currentPhotoData);
                };
                reader.readAsDataURL(file);
            }
        }

        // Analyze water quality
        function analyzeWaterQuality(photoData) {
            fetch('/analyze_water', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ photo_data: photoData })
            })
            .then(response => response.json())
            .then(data => {
                const resultDiv = document.getElementById('analysisResult');
                const cleanlinessLevel = data.cleanliness_level;
                const confidence = (data.confidence_score * 100).toFixed(1);
                
                let bgColor, textColor, emoji;
                switch(cleanlinessLevel) {
                    case 'clean':
                        bgColor = 'bg-green-100';
                        textColor = 'text-green-800';
                        emoji = '✅';
                        break;
                    case 'muddy':
                        bgColor = 'bg-yellow-100';
                        textColor = 'text-yellow-800';
                        emoji = '⚠️';
                        break;
                    case 'contaminated':
                        bgColor = 'bg-red-100';
                        textColor = 'text-red-800';
                        emoji = '❌';
                        break;
                    default:
                        bgColor = 'bg-gray-100';
                        textColor = 'text-gray-800';
                        emoji = '❓';
                }
                
                resultDiv.className = `mt-2 p-2 rounded text-sm ${bgColor} ${textColor}`;
                resultDiv.innerHTML = `${emoji} <strong>${cleanlinessLevel.charAt(0).toUpperCase() + cleanlinessLevel.slice(1)}</strong> (${confidence}% confidence)`;
            })
            .catch(error => {
                console.error('Error analyzing water:', error);
                const resultDiv = document.getElementById('analysisResult');
                resultDiv.className = 'mt-2 p-2 rounded text-sm bg-red-100 text-red-800';
                resultDiv.innerHTML = '❌ Analysis failed';
            });
        }

        // Submit water source form
        document.getElementById('waterSourceForm').addEventListener('submit', function(e) {
            e.preventDefault();
            
            if (!selectedLatLng) {
                alert('Please click on the map to select a location first!');
                return;
            }
            
            const formData = {
                name: document.getElementById('sourceName').value,
                latitude: selectedLatLng.lat,
                longitude: selectedLatLng.lng,
                water_type: document.getElementById('waterType').value,
                notes: document.getElementById('notes').value,
                photo_data: currentPhotoData,
                added_by: currentUsername
            };
            
            fetch('/add_water_source', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(formData)
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    // Reset form
                    document.getElementById('waterSourceForm').reset();
                    document.getElementById('photoPreview').classList.add('hidden');
                    document.getElementById('latitude').value = '';
                    document.getElementById('longitude').value = '';
                    
                    // Remove temporary marker
                    if (window.tempMarker) {
                        map.removeLayer(window.tempMarker);
                    }
                    
                    // Reload water sources
                    loadWaterSources();
                    
                    selectedLatLng = null;
                    currentPhotoData = null;
                    
                    alert('Water source added successfully!');
                } else {
                    alert('Error adding water source: ' + data.error);
                }
            })
            .catch(error => {
                console.error('Error:', error);
                alert('Error adding water source');
            });
        });

        // Load water sources from database
        function loadWaterSources() {
            fetch('/get_water_sources')
            .then(response => response.json())
            .then(data => {
                // Clear existing markers
                waterSourceMarkers.forEach(marker => map.removeLayer(marker));
                waterSourceMarkers = [];
                
                // Add markers for each water source
                data.forEach(source => {
                    const marker = createWaterSourceMarker(source);
                    waterSourceMarkers.push(marker);
                    marker.addTo(map);
                });
                
                // Update nearby sources list
                updateNearbyWaterSources(data);
            })
            .catch(error => {
                console.error('Error loading water sources:', error);
            });
            
            // Load alerts if admin
            if (isAdmin) {
                loadAlerts();
            }
        }

        // Create marker for water source
        function createWaterSourceMarker(source) {
            const displayQuality = source.admin_override || source.cleanliness_level;
            let color, emoji;
            switch(displayQuality) {
                case 'clean':
                    color = '#10b981';
                    emoji = '💧';
                    break;
                case 'muddy':
                    color = '#f59e0b';
                    emoji = '🟡';
                    break;
                case 'contaminated':
                    color = '#ef4444';
                    emoji = '🔴';
                    break;
                default:
                    color = '#6b7280';
                    emoji = '❓';
            }
            
            const marker = L.marker([source.latitude, source.longitude], {
                icon: L.divIcon({
                    className: 'water-marker',
                    html: `<div style="background-color: ${color}; color: white; width: 30px; height: 30px; border-radius: 50%; display: flex; align-items: center; justify-content: center; border: 2px solid white; box-shadow: 0 2px 4px rgba(0,0,0,0.2); font-size: 16px;">${emoji}</div>`,
                    iconSize: [30, 30],
                    iconAnchor: [15, 15]
                })
            });
            
            const confidence = source.confidence_score ? (source.confidence_score * 100).toFixed(1) : 'N/A';
            const qualityDisplay = source.admin_override ? 
                `${displayQuality} (Admin Override)` : 
                `${displayQuality} (${confidence}% confidence)`;
            
            // Simple popup with basic info
            marker.bindPopup(`
                <div class="p-2">
                    <h4 class="font-bold text-lg">${source.name}</h4>
                    <p><strong>Type:</strong> ${source.water_type}</p>
                    <p><strong>Quality:</strong> ${qualityDisplay}</p>
                    <p><strong>Added by:</strong> ${source.added_by}</p>
                    <button onclick="showWaterSourceDetails(${source.id})" class="mt-2 w-full bg-blue-500 text-white py-1 px-3 rounded text-sm hover:bg-blue-600 transition">
                        📋 View Full Details
                    </button>
                </div>
            `);
            
            return marker;
        }

        // Show detailed water source information in the details panel
        function showWaterSourceDetails(sourceId) {
            const detailsPanel = document.getElementById('detailsPanel');
            const detailsContent = document.getElementById('detailsContent');
            
            // Show loading state
            detailsPanel.classList.remove('hidden');
            detailsContent.innerHTML = '<div class="text-center py-8"><div class="inline-block animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div><p class="mt-2 text-gray-600">Loading details...</p></div>';
            
            // Scroll to details panel
            detailsPanel.scrollIntoView({ behavior: 'smooth' });
            
            Promise.all([
                fetch(`/get_water_source_details/${sourceId}`).then(r => r.json()),
                fetch(`/get_votes/${sourceId}`).then(r => r.json()),
                fetch(`/get_comments/${sourceId}`).then(r => r.json())
            ])
            .then(([source, votes, comments]) => {
                const confidence = source.confidence_score ? (source.confidence_score * 100).toFixed(1) : 'N/A';
                const upvotes = votes.filter(v => v.vote_type === 'upvote').length;
                const downvotes = votes.filter(v => v.vote_type === 'downvote').length;
                const userVote = votes.find(v => v.username === currentUsername);
                const displayQuality = source.admin_override || source.cleanliness_level;
                
                detailsContent.innerHTML = `
                    <div class="space-y-6">
                        <!-- Basic Information -->
                        <div>
                            <h4 class="text-2xl font-bold text-gray-800 mb-4">${source.name}</h4>
                            <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
                                <div class="space-y-3">
                                    <div>
                                        <span class="font-medium text-gray-700">Type:</span>
                                        <span class="ml-2 px-2 py-1 bg-gray-100 rounded text-sm">${source.water_type}</span>
                                    </div>
                                    <div>
                                        <span class="font-medium text-gray-700">Quality:</span>
                                        <span class="ml-2 px-2 py-1 ${getQualityBadgeClass(displayQuality)} rounded text-sm">
                                            ${displayQuality} 
                                            ${source.admin_override ? '<span class="text-xs">(Admin Override)</span>' : `(${confidence}% confidence)`}
                                        </span>
                                    </div>
                                    <div>
                                        <span class="font-medium text-gray-700">Added by:</span>
                                        <span class="ml-2">${source.added_by}</span>
                                    </div>
                                    <div>
                                        <span class="font-medium text-gray-700">Date added:</span>
                                        <span class="ml-2">${new Date(source.timestamp).toLocaleDateString()}</span>
                                    </div>
                                </div>
                                <div class="space-y-3">
                                    <div>
                                        <span class="font-medium text-gray-700">Coordinates:</span>
                                        <div class="ml-2 text-sm font-mono bg-gray-100 px-2 py-1 rounded">
                                            ${source.latitude.toFixed(6)}, ${source.longitude.toFixed(6)}
                                        </div>
                                    </div>
                                    ${source.notes ? `
                                        <div>
                                            <span class="font-medium text-gray-700">Notes:</span>
                                            <div class="ml-2 mt-1 p-3 bg-gray-50 rounded text-sm">${source.notes}</div>
                                        </div>
                                    ` : ''}
                                </div>
                            </div>
                        </div>

                        ${isAdmin ? `
                        <!-- Admin Controls -->
                        <div class="border-t border-gray-200 pt-6">
                            <div class="bg-blue-50 p-4 rounded-lg">
                                <h5 class="text-lg font-semibold text-blue-800 mb-3 flex items-center">
                                    🛡️ Admin Controls
                                    <span class="ml-2 px-2 py-1 bg-blue-200 text-blue-800 text-xs rounded-full">ADMIN</span>
                                </h5>
                                <div class="flex space-x-2 mb-3">
                                    <button onclick="adminOverride(${sourceId}, 'clean')" class="px-3 py-2 bg-green-500 text-white rounded text-sm hover:bg-green-600 transition">
                                        Mark as Clean
                                    </button>
                                    <button onclick="adminOverride(${sourceId}, 'muddy')" class="px-3 py-2 bg-yellow-500 text-white rounded text-sm hover:bg-yellow-600 transition">
                                        Mark as Muddy
                                    </button>
                                    <button onclick="adminOverride(${sourceId}, 'contaminated')" class="px-3 py-2 bg-red-500 text-white rounded text-sm hover:bg-red-600 transition">
                                        Mark as Contaminated
                                    </button>
                                </div>
                                <p class="text-xs text-blue-700">Admin overrides will take precedence over automatic analysis</p>
                            </div>
                        </div>
                        ` : ''}

                        <!-- Community Feedback Section -->
                        <div class="border-t border-gray-200 pt-6">
                            <div class="flex items-center justify-between mb-4">
                                <h5 class="text-lg font-semibold text-gray-800">Community Feedback</h5>
                                <div class="flex items-center space-x-4">
                                    <span class="flex items-center text-green-600">
                                        <svg class="w-5 h-5 mr-1" fill="currentColor" viewBox="0 0 20 20">
                                            <path d="M2 10.5a1.5 1.5 0 113 0v6a1.5 1.5 0 01-3 0v-6zM6 10.333v5.43a2 2 0 001.106 1.79l.05.025A4 4 0 008.943 18h5.416a2 2 0 001.962-1.608l1.2-6A2 2 0 0015.56 8H12V4a2 2 0 00-2-2 1 1 0 00-1 1v.667a4 4 0 01-.8 2.4L6.8 7.933a4 4 0 00-.8 2.4z"></path>
                                        </svg>
                                        ${upvotes}
                                    </span>
                                    <span class="flex items-center text-red-600">
                                        <svg class="w-5 h-5 mr-1" fill="currentColor" viewBox="0 0 20 20">
                                            <path d="M18 9.5a1.5 1.5 0 11-3 0v-6a1.5 1.5 0 013 0v6zM14 9.667v-5.43a2 2 0 00-1.106-1.79l-.05-.025A4 4 0 0011.057 2H5.641a2 2 0 00-1.962 1.608l-1.2 6A2 2 0 004.44 12H8v4a2 2 0 002 2 1 1 0 001-1v-.667a4 4 0 01.8-2.4l1.4-1.866a4 4 0 00.8-2.4z"></path>
                                        </svg>
                                        ${downvotes}
                                    </span>
                                </div>
                            </div>
                            
                            <div class="flex space-x-3 mb-6">
                                <button onclick="vote(${sourceId}, 'upvote')" class="flex-1 py-3 px-4 rounded-lg font-medium transition ${userVote?.vote_type === 'upvote' ? 'bg-green-500 text-white' : 'bg-gray-100 text-gray-700 hover:bg-green-100'}">
                                    👍 Accurate Information
                                </button>
                                <button onclick="vote(${sourceId}, 'downvote')" class="flex-1 py-3 px-4 rounded-lg font-medium transition ${userVote?.vote_type === 'downvote' ? 'bg-red-500 text-white' : 'bg-gray-100 text-gray-700 hover:bg-red-100'}">
                                    👎 Inaccurate Information
                                </button>
                            </div>
                        </div>

                        <!-- Comments Section -->
                        <div class="border-t border-gray-200 pt-6">
                            <h5 class="text-lg font-semibold text-gray-800 mb-4">Comments & Additional Info</h5>
                            
                            <!-- Add Comment -->
                            <div class="mb-6">
                                <textarea id="commentText_${sourceId}" placeholder="Share additional information about this water source..." class="w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 resize-none" rows="3"></textarea>
                                <button onclick="addComment(${sourceId})" class="mt-3 px-6 py-2 bg-blue-500 text-white rounded-lg hover:bg-blue-600 transition font-medium">
                                    💬 Add Comment
                                </button>
                            </div>
                            
                            <!-- Comments List -->
                            <div class="space-y-4">
                                ${comments.length === 0 ? '<p class="text-gray-500 text-center py-4">No comments yet. Be the first to share additional information!</p>' : ''}
                                ${comments.map(comment => `
                                    <div class="${comment.is_admin ? 'bg-blue-50 border-l-4 border-blue-500' : 'bg-gray-50'} p-4 rounded-lg">
                                        <div class="flex items-center justify-between mb-2">
                                            <div class="flex items-center">
                                                <span class="font-medium text-gray-800">${comment.username}</span>
                                                ${comment.is_admin ? '<span class="ml-2 px-2 py-1 bg-blue-200 text-blue-800 text-xs rounded-full">ADMIN</span>' : ''}
                                                ${comment.is_admin ? '<span class="ml-2 text-blue-600">📌</span>' : ''}
                                            </div>
                                            <span class="text-gray-400 text-sm">${new Date(comment.timestamp).toLocaleDateString()}</span>
                                        </div>
                                        <p class="text-gray-700 ${comment.is_admin ? 'font-medium' : ''}">${comment.comment}</p>
                                    </div>
                                `).join('')}
                            </div>
                        </div>

                        <!-- Close Button -->
                        <div class="border-t border-gray-200 pt-6">
                            <button onclick="hideWaterSourceDetails()" class="w-full py-3 px-4 bg-gray-100 text-gray-700 rounded-lg hover:bg-gray-200 transition font-medium">
                                ✕ Close Details
                            </button>
                        </div>
                    </div>
                `;
            })
            .catch(error => {
                console.error('Error loading water source details:', error);
                detailsContent.innerHTML = '<div class="text-center py-8 text-red-600">Error loading details. Please try again.</div>';
            });
        }

        // Hide the details panel
        function hideWaterSourceDetails() {
            document.getElementById('detailsPanel').classList.add('hidden');
        }

        // Get CSS class for quality badge
        function getQualityBadgeClass(quality) {
            switch(quality) {
                case 'clean':
                    return 'bg-green-100 text-green-800';
                case 'muddy':
                    return 'bg-yellow-100 text-yellow-800';
                case 'contaminated':
                    return 'bg-red-100 text-red-800';
                default:
                    return 'bg-gray-100 text-gray-800';
            }
        }

        // Vote on water source
        function vote(sourceId, voteType) {
            fetch('/vote', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    water_source_id: sourceId,
                    username: currentUsername,
                    vote_type: voteType
                })
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    // Refresh the details panel to show updated votes
                    showWaterSourceDetails(sourceId);
                } else {
                    alert('Error voting: ' + data.error);
                }
            })
            .catch(error => {
                console.error('Error voting:', error);
                alert('Error submitting vote');
            });
        }

        // Add comment to water source
        function addComment(sourceId) {
            const commentText = document.getElementById(`commentText_${sourceId}`).value.trim();
            if (!commentText) {
                alert('Please enter a comment');
                return;
            }
            
            fetch('/add_comment', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    water_source_id: sourceId,
                    username: currentUsername,
                    comment: commentText,
                    is_admin: isAdmin
                })
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    // Refresh the details panel to show new comment
                    showWaterSourceDetails(sourceId);
                } else {
                    alert('Error adding comment: ' + data.error);
                }
            })
            .catch(error => {
                console.error('Error adding comment:', error);
                alert('Error submitting comment');
            });
        }

        // Admin override water source quality
        function adminOverride(sourceId, quality) {
            if (!isAdmin) {
                alert('Admin access required');
                return;
            }
            
            fetch('/admin_override', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    water_source_id: sourceId,
                    quality: quality,
                    admin_username: currentUsername
                })
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    // Refresh the details panel and reload markers
                    showWaterSourceDetails(sourceId);
                    loadWaterSources();
                } else {
                    alert('Error updating water source: ' + data.error);
                }
            })
            .catch(error => {
                console.error('Error updating water source:', error);
                alert('Error updating water source');
            });
        }

        // Load alerts for admin
        function loadAlerts() {
            if (!isAdmin) return;
            
            fetch('/get_alerts')
            .then(response => response.json())
            .then(data => {
                // Clear existing alert markers
                alertMarkers.forEach(marker => map.removeLayer(marker));
                alertMarkers = [];
                
                // Add markers for each alert
                data.forEach(alert => {
                    const marker = createAlertMarker(alert);
                    alertMarkers.push(marker);
                    marker.addTo(map);
                });
                
                // Update alerts list
                updateAlertsNearMe(data);
            })
            .catch(error => {
                console.error('Error loading alerts:', error);
            });
        }

        // Create alert marker
        function createAlertMarker(alert) {
            const marker = L.marker([alert.latitude, alert.longitude], {
                icon: L.divIcon({
                    className: 'alert-marker',
                    html: '<div style="background-color: #ef4444; color: white; width: 30px; height: 30px; border-radius: 50%; display: flex; align-items: center; justify-content: center; border: 2px solid white; box-shadow: 0 2px 4px rgba(0,0,0,0.2); font-size: 16px;">🚨</div>',
                    iconSize: [30, 30],
                    iconAnchor: [15, 15]
                })
            });
            
            marker.bindPopup(`
                <div class="p-2">
                    <h4 class="font-bold text-lg text-red-600">⚠️ ${alert.title}</h4>
                    <p class="text-sm mt-2">${alert.message}</p>
                    <p class="text-xs text-gray-500 mt-2">Posted by ${alert.added_by}</p>
                    <p class="text-xs text-gray-500">${new Date(alert.timestamp).toLocaleDateString()}</p>
                </div>
            `);
            
            return marker;
        }

        // Update alerts near me list
        function updateAlertsNearMe(alerts = null) {
            if (!isAdmin) return;
            
            const container = document.getElementById('alertsContainer');
            
            if (!userLocation) {
                container.innerHTML = `
                    <div class="text-center py-4 text-gray-500">
                        <p class="text-sm">Click "Find Me" to see nearby alerts</p>
                    </div>
                `;
                return;
            }
            
            if (!alerts) {
                fetch('/get_alerts')
                .then(response => response.json())
                .then(data => updateAlertsNearMe(data))
                .catch(error => console.error('Error fetching alerts:', error));
                return;
            }
            
            // Calculate distances and sort by proximity
            const alertsWithDistance = alerts.map(alert => ({
                ...alert,
                distance: calculateDistance(
                    userLocation.latitude, 
                    userLocation.longitude,
                    alert.latitude, 
                    alert.longitude
                )
            })).sort((a, b) => a.distance - b.distance);
            
            if (alertsWithDistance.length === 0) {
                container.innerHTML = `
                    <div class="text-center py-4 text-gray-500">
                        <p class="text-sm">No alerts in your area</p>
                    </div>
                `;
                return;
            }
            
            // Display nearest alerts
            const nearestAlerts = alertsWithDistance.slice(0, 5);
            
            container.innerHTML = nearestAlerts.map(alert => `
                <div class="p-3 border border-red-200 bg-red-50 rounded-lg">
                    <div class="flex items-start justify-between">
                        <div class="flex-1">
                            <h4 class="font-medium text-red-800 mb-1">🚨 ${alert.title}</h4>
                            <p class="text-sm text-red-700 mb-2">${alert.message}</p>
                            <div class="text-xs text-red-600">
                                ${formatDistance(alert.distance)} away • ${new Date(alert.timestamp).toLocaleDateString()}
                            </div>
                        </div>
                    </div>
                </div>
            `).join('');
        }

        // Handle alert form submission
        document.getElementById('alertForm').addEventListener('submit', function(e) {
            e.preventDefault();
            
            if (!isAdmin) {
                alert('Admin access required');
                return;
            }
            
            const title = document.getElementById('alertTitle').value.trim();
            const message = document.getElementById('alertMessage').value.trim();
            const latitude = document.getElementById('alertLatitude').value;
            const longitude = document.getElementById('alertLongitude').value;
            
            if (!title || !message) {
                alert('Please fill in all fields');
                return;
            }
            
            if (!latitude || !longitude) {
                alert('Please click on the map to set alert location');
                return;
            }
            
            fetch('/add_alert', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    title: title,
                    message: message,
                    latitude: parseFloat(latitude),
                    longitude: parseFloat(longitude),
                    added_by: currentUsername
                })
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    // Reset form
                    document.getElementById('alertForm').reset();
                    document.getElementById('alertLatitude').value = '';
                    document.getElementById('alertLongitude').value = '';
                    
                    // Remove temporary marker
                    if (window.tempAlertMarker) {
                        map.removeLayer(window.tempAlertMarker);
                        window.tempAlertMarker = null;
                    }
                    
                    // Reload alerts
                    loadAlerts();
                    
                    alert('Alert added successfully!');
                } else {
                    alert('Error adding alert: ' + data.error);
                }
            })
            .catch(error => {
                console.error('Error adding alert:', error);
                alert('Error adding alert');
            });
        });

        // Toggle alert mode for admin
        function toggleAlertMode() {
            if (!isAdmin) return;
            alertMode = !alertMode;
            // You could add visual feedback here if needed
        }

        // Calculate distance between two points using Haversine formula
        function calculateDistance(lat1, lon1, lat2, lon2) {
            const R = 6371; // Radius of the Earth in kilometers
            const dLat = (lat2 - lat1) * Math.PI / 180;
            const dLon = (lon2 - lon1) * Math.PI / 180;
            const a = 
                Math.sin(dLat/2) * Math.sin(dLat/2) +
                Math.cos(lat1 * Math.PI / 180) * Math.cos(lat2 * Math.PI / 180) * 
                Math.sin(dLon/2) * Math.sin(dLon/2);
            const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1-a));
            const distance = R * c; // Distance in kilometers
            return distance;
        }

        // Format distance for display
        function formatDistance(distanceKm) {
            if (distanceKm < 1) {
                return Math.round(distanceKm * 1000) + 'm';
            } else if (distanceKm < 10) {
                return distanceKm.toFixed(1) + 'km';
            } else {
                return Math.round(distanceKm) + 'km';
            }
        }

        // Update nearby water sources list
        function updateNearbyWaterSources(sources = null) {
            const container = document.getElementById('nearbySourcesContainer');
            
            if (!userLocation) {
                container.innerHTML = `
                    <div class="text-center py-8 text-gray-500">
                        <svg class="w-12 h-12 mx-auto mb-3 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M17.657 16.657L13.414 20.9a1.998 1.998 0 01-2.827 0l-4.244-4.243a8 8 0 1111.314 0z"></path>
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 11a3 3 0 11-6 0 3 3 0 016 0z"></path>
                        </svg>
                        <p>Click "Find Me" to see nearby water sources</p>
                    </div>
                `;
                return;
            }
            
            // If sources not provided, fetch them
            if (!sources) {
                fetch('/get_water_sources')
                .then(response => response.json())
                .then(data => updateNearbyWaterSources(data))
                .catch(error => console.error('Error fetching water sources:', error));
                return;
            }
            
            // Calculate distances and sort by proximity
            const sourcesWithDistance = sources.map(source => ({
                ...source,
                distance: calculateDistance(
                    userLocation.latitude, 
                    userLocation.longitude,
                    source.latitude, 
                    source.longitude
                )
            })).sort((a, b) => a.distance - b.distance);
            
            if (sourcesWithDistance.length === 0) {
                container.innerHTML = `
                    <div class="text-center py-8 text-gray-500">
                        <svg class="w-12 h-12 mx-auto mb-3 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9.172 16.172a4 4 0 015.656 0M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"></path>
                        </svg>
                        <p>No water sources found</p>
                        <p class="text-sm mt-1">Start by adding some water sources to the map!</p>
                    </div>
                `;
                return;
            }
            
            // Display top 10 nearest sources
            const nearestSources = sourcesWithDistance.slice(0, 10);
            
            container.innerHTML = nearestSources.map(source => {
                const displayQuality = source.admin_override || source.cleanliness_level;
                const qualityColor = getQualityColor(displayQuality);
                const qualityEmoji = getQualityEmoji(displayQuality);
                
                return `
                    <div onclick="navigateToWaterSource(${source.id}, ${source.latitude}, ${source.longitude})" 
                         class="p-3 border border-gray-200 rounded-lg hover:bg-gray-50 cursor-pointer transition">
                        <div class="flex items-center justify-between">
                            <div class="flex-1">
                                <div class="flex items-center mb-1">
                                    <span class="text-lg mr-2">${qualityEmoji}</span>
                                    <h4 class="font-medium text-gray-800 truncate">${source.name}</h4>
                                    ${source.admin_override ? '<span class="ml-2 px-1 py-0.5 bg-blue-200 text-blue-800 text-xs rounded">ADMIN</span>' : ''}
                                </div>
                                <div class="flex items-center text-sm text-gray-600">
                                    <span class="px-2 py-1 ${qualityColor} rounded text-xs mr-2">${displayQuality}</span>
                                    <span>${source.water_type}</span>
                                </div>
                                <div class="text-xs text-gray-500 mt-1">
                                    Added by ${source.added_by}
                                </div>
                            </div>
                            <div class="text-right ml-3">
                                <div class="text-sm font-medium text-blue-600">${formatDistance(source.distance)}</div>
                                <div class="text-xs text-gray-500">away</div>
                            </div>
                        </div>
                    </div>
                `;
            }).join('');
        }

        // Navigate to water source on map and show details
        function navigateToWaterSource(sourceId, latitude, longitude) {
            // Center map on the water source
            map.setView([latitude, longitude], 16);
            
            // Find and open the marker popup
            const marker = waterSourceMarkers.find(m => {
                const markerLatLng = m.getLatLng();
                return Math.abs(markerLatLng.lat - latitude) < 0.0001 && 
                       Math.abs(markerLatLng.lng - longitude) < 0.0001;
            });
            
            if (marker) {
                marker.openPopup();
            }
            
            // Show details in the panel
            showWaterSourceDetails(sourceId);
        }

        // Get quality color for badges
        function getQualityColor(quality) {
            switch(quality) {
                case 'clean':
                    return 'bg-green-100 text-green-800';
                case 'muddy':
                    return 'bg-yellow-100 text-yellow-800';
                case 'contaminated':
                    return 'bg-red-100 text-red-800';
                default:
                    return 'bg-gray-100 text-gray-800';
            }
        }

        // Get quality emoji
        function getQualityEmoji(quality) {
            switch(quality) {
                case 'clean':
                    return '💧';
                case 'muddy':
                    return '🟡';
                case 'contaminated':
                    return '🔴';
                default:
                    return '❓';
            }
        }
    </script>
</body>
</html>
'''

@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)

@app.route('/analyze_water', methods=['POST'])
def analyze_water():
    try:
        data = request.get_json()
        photo_data = data.get('photo_data')
        
        if not photo_data:
            return jsonify({'error': 'No photo data provided'}), 400
        
        cleanliness_level, confidence_score = classifier.analyze_water_image(photo_data)
        
        return jsonify({
            'cleanliness_level': cleanliness_level,
            'confidence_score': confidence_score
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/add_water_source', methods=['POST'])
def add_water_source():
    try:
        data = request.get_json()
        
        # Analyze photo if provided
        cleanliness_level = None
        confidence_score = None
        if data.get('photo_data'):
            cleanliness_level, confidence_score = classifier.analyze_water_image(data['photo_data'])
        
        # Save to database
        conn = sqlite3.connect('water_sources.db')
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO water_sources 
            (name, latitude, longitude, water_type, cleanliness_level, confidence_score, notes, photo_data, added_by)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            data['name'],
            data['latitude'],
            data['longitude'],
            data['water_type'],
            cleanliness_level,
            confidence_score,
            data.get('notes', ''),
            data.get('photo_data', ''),
            data.get('added_by', 'Anonymous')
        ))
        conn.commit()
        conn.close()
        
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/get_water_sources')
def get_water_sources():
    try:
        conn = sqlite3.connect('water_sources.db')
        conn.row_factory = sqlite3.Row  # This allows us to access columns by name
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM water_sources ORDER BY timestamp DESC')
        
        sources = []
        for row in cursor.fetchall():
            sources.append({
                'id': row['id'],
                'name': row['name'],
                'latitude': row['latitude'],
                'longitude': row['longitude'],
                'water_type': row['water_type'],
                'cleanliness_level': row['cleanliness_level'],
                'confidence_score': row['confidence_score'],
                'notes': row['notes'],
                'added_by': row['added_by'] if row['added_by'] else 'Anonymous',
                'admin_override': row['admin_override'] if 'admin_override' in row.keys() else None,
                'timestamp': row['timestamp']
            })
        
        conn.close()
        return jsonify(sources)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/get_water_source_details/<int:source_id>')
def get_water_source_details(source_id):
    try:
        conn = sqlite3.connect('water_sources.db')
        conn.row_factory = sqlite3.Row  # This allows us to access columns by name
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM water_sources WHERE id = ?', (source_id,))
        
        row = cursor.fetchone()
        if row:
            source = {
                'id': row['id'],
                'name': row['name'],
                'latitude': row['latitude'],
                'longitude': row['longitude'],
                'water_type': row['water_type'],
                'cleanliness_level': row['cleanliness_level'],
                'confidence_score': row['confidence_score'],
                'notes': row['notes'],
                'added_by': row['added_by'] if row['added_by'] else 'Anonymous',
                'admin_override': row['admin_override'] if 'admin_override' in row.keys() else None,
                'timestamp': row['timestamp']
            }
            conn.close()
            return jsonify(source)
        else:
            conn.close()
            return jsonify({'error': 'Water source not found'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/get_votes/<int:source_id>')
def get_votes(source_id):
    try:
        conn = sqlite3.connect('water_sources.db')
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM votes WHERE water_source_id = ?', (source_id,))
        
        votes = []
        for row in cursor.fetchall():
            votes.append({
                'id': row[0],
                'water_source_id': row[1],
                'username': row[2],
                'vote_type': row[3],
                'timestamp': row[4]
            })
        
        conn.close()
        return jsonify(votes)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/get_comments/<int:source_id>')
def get_comments(source_id):
    try:
        conn = sqlite3.connect('water_sources.db')
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM comments WHERE water_source_id = ? ORDER BY is_admin DESC, timestamp DESC', (source_id,))
        
        comments = []
        for row in cursor.fetchall():
            comments.append({
                'id': row[0],
                'water_source_id': row[1],
                'username': row[2],
                'comment': row[3],
                'is_admin': row[4] if len(row) > 4 else False,
                'timestamp': row[5] if len(row) > 5 else row[4]
            })
        
        conn.close()
        return jsonify(comments)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/vote', methods=['POST'])
def vote():
    try:
        data = request.get_json()
        water_source_id = data['water_source_id']
        username = data['username']
        vote_type = data['vote_type']
        
        conn = sqlite3.connect('water_sources.db')
        cursor = conn.cursor()
        
        # Replace existing vote or insert new one
        cursor.execute('''
            INSERT OR REPLACE INTO votes (water_source_id, username, vote_type)
            VALUES (?, ?, ?)
        ''', (water_source_id, username, vote_type))
        
        conn.commit()
        conn.close()
        
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/add_comment', methods=['POST'])
def add_comment():
    try:
        data = request.get_json()
        water_source_id = data['water_source_id']
        username = data['username']
        comment = data['comment']
        is_admin = data.get('is_admin', False)
        
        conn = sqlite3.connect('water_sources.db')
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO comments (water_source_id, username, comment, is_admin)
            VALUES (?, ?, ?, ?)
        ''', (water_source_id, username, comment, is_admin))
        
        conn.commit()
        conn.close()
        
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/admin_override', methods=['POST'])
def admin_override():
    try:
        data = request.get_json()
        water_source_id = data['water_source_id']
        quality = data['quality']
        admin_username = data['admin_username']
        
        # Verify admin access
        if admin_username.lower() != 'admin':
            return jsonify({'success': False, 'error': 'Admin access required'}), 403
        
        conn = sqlite3.connect('water_sources.db')
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE water_sources 
            SET admin_override = ?
            WHERE id = ?
        ''', (quality, water_source_id))
        
        conn.commit()
        conn.close()
        
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/get_alerts')
def get_alerts():
    try:
        conn = sqlite3.connect('water_sources.db')
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM alerts ORDER BY timestamp DESC')
        
        alerts = []
        for row in cursor.fetchall():
            alerts.append({
                'id': row[0],
                'title': row[1],
                'message': row[2],
                'latitude': row[3],
                'longitude': row[4],
                'alert_type': row[5],
                'added_by': row[6],
                'timestamp': row[7]
            })
        
        conn.close()
        return jsonify(alerts)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/add_alert', methods=['POST'])
def add_alert():
    try:
        data = request.get_json()
        
        # Verify admin access
        if data.get('added_by', '').lower() != 'admin':
            return jsonify({'success': False, 'error': 'Admin access required'}), 403
        
        conn = sqlite3.connect('water_sources.db')
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO alerts (title, message, latitude, longitude, added_by)
            VALUES (?, ?, ?, ?, ?)
        ''', (
            data['title'],
            data['message'],
            data['latitude'],
            data['longitude'],
            data['added_by']
        ))
        
        conn.commit()
        conn.close()
        
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

if __name__ == '__main__':
    # Initialize database
    init_db()
    
    print("Where's the Well? - Water Source Locator")
    print("=" * 50)
    print("Starting application...")
    print("Open your browser and go to: http://localhost:5000")
    
    # Run the Flask app
    app.run(debug=True, host='0.0.0.0', port=5000)
