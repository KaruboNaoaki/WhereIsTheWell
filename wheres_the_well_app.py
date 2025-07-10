#!/usr/bin/env python3
"""
Where's the Well? - Interactive Water Source Locator
A desktop application for logging and evaluating water sources offline.
"""

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
    </style>
</head>
<body class="bg-gray-100 min-h-screen">
    <!-- Header -->
    <header class="bg-blue-600 text-white shadow-lg">
        <div class="container mx-auto px-4 py-6">
            <h1 class="text-3xl font-bold flex items-center">
                <svg class="w-8 h-8 mr-3" fill="currentColor" viewBox="0 0 20 20">
                    <path fill-rule="evenodd" d="M5.05 4.05a7 7 0 119.9 9.9L10 18.9l-4.95-4.95a7 7 0 010-9.9zM10 11a2 2 0 100-4 2 2 0 000 4z" clip-rule="evenodd"></path>
                </svg>
                Where's the Well?
            </h1>
            <p class="text-blue-100 mt-2">Interactive Water Source Locator</p>
        </div>
    </header>

    <!-- Main Content -->
    <div class="container mx-auto px-4 py-8">
        <div class="grid grid-cols-1 lg:grid-cols-3 gap-8">
            
            <!-- Map Column -->
            <div class="lg:col-span-2">
                <div class="bg-white rounded-xl shadow-lg overflow-hidden">
                    <div class="p-6 border-b border-gray-200">
                        <h2 class="text-xl font-semibold text-gray-800 flex items-center">
                            <svg class="w-5 h-5 mr-2" fill="currentColor" viewBox="0 0 20 20">
                                <path fill-rule="evenodd" d="M12 1.586l-4 4v12.828l4-4V1.586zM3.707 3.293A1 1 0 002 4v10a1 1 0 00.293.707L6 18.414V5.586L3.707 3.293zM17.707 5.293L14 1.586v12.828l3.707 3.707A1 1 0 0018 18V8a1 1 0 00-.293-.707z" clip-rule="evenodd"></path>
                            </svg>
                            Interactive Map
                        </h2>
                        <p class="text-gray-600 text-sm mt-1">Click on the map to add a new water source</p>
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

                <!-- Stats Card -->
                <div class="bg-white rounded-xl shadow-lg p-6">
                    <h3 class="text-lg font-semibold text-gray-800 mb-4">Water Sources Summary</h3>
                    <div id="statsContainer" class="space-y-3">
                        <div class="flex justify-between items-center p-3 bg-green-50 rounded-lg">
                            <div class="flex items-center">
                                <div class="w-3 h-3 bg-green-500 rounded-full mr-3"></div>
                                <span class="font-medium">Clean</span>
                            </div>
                            <span id="cleanCount" class="font-bold text-green-600">0</span>
                        </div>
                        <div class="flex justify-between items-center p-3 bg-yellow-50 rounded-lg">
                            <div class="flex items-center">
                                <div class="w-3 h-3 bg-yellow-500 rounded-full mr-3"></div>
                                <span class="font-medium">Muddy</span>
                            </div>
                            <span id="muddyCount" class="font-bold text-yellow-600">0</span>
                        </div>
                        <div class="flex justify-between items-center p-3 bg-red-50 rounded-lg">
                            <div class="flex items-center">
                                <div class="w-3 h-3 bg-red-500 rounded-full mr-3"></div>
                                <span class="font-medium">Contaminated</span>
                            </div>
                            <span id="contaminatedCount" class="font-bold text-red-600">0</span>
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
        let selectedLatLng = null;
        let currentPhotoData = null;

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

            // Add click event for placing water sources
            map.on('click', function(e) {
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
                    },
                    function(error) {
                        console.log("Geolocation error:", error);
                        // Use default location if geolocation fails
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
                photo_data: currentPhotoData
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
                
                // Update stats
                updateStats(data);
            })
            .catch(error => {
                console.error('Error loading water sources:', error);
            });
        }

        // Create marker for water source
        function createWaterSourceMarker(source) {
            let color, emoji;
            switch(source.cleanliness_level) {
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
            
            marker.bindPopup(`
                <div class="p-2">
                    <h4 class="font-bold text-lg">${source.name}</h4>
                    <p><strong>Type:</strong> ${source.water_type}</p>
                    <p><strong>Quality:</strong> ${source.cleanliness_level} (${confidence}% confidence)</p>
                    <p><strong>Location:</strong> ${source.latitude.toFixed(4)}, ${source.longitude.toFixed(4)}</p>
                    ${source.notes ? `<p><strong>Notes:</strong> ${source.notes}</p>` : ''}
                    <p class="text-sm text-gray-500 mt-2">${new Date(source.timestamp).toLocaleDateString()}</p>
                </div>
            `);
            
            return marker;
        }

        // Update statistics
        function updateStats(sources) {
            const stats = sources.reduce((acc, source) => {
                acc[source.cleanliness_level] = (acc[source.cleanliness_level] || 0) + 1;
                return acc;
            }, {});
            
            document.getElementById('cleanCount').textContent = stats.clean || 0;
            document.getElementById('muddyCount').textContent = stats.muddy || 0;
            document.getElementById('contaminatedCount').textContent = stats.contaminated || 0;
        }

        // Initialize app when page loads
        document.addEventListener('DOMContentLoaded', function() {
            initMap();
        });
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
            (name, latitude, longitude, water_type, cleanliness_level, confidence_score, notes, photo_data)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            data['name'],
            data['latitude'],
            data['longitude'],
            data['water_type'],
            cleanliness_level,
            confidence_score,
            data.get('notes', ''),
            data.get('photo_data', '')
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
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM water_sources ORDER BY timestamp DESC')
        
        sources = []
        for row in cursor.fetchall():
            sources.append({
                'id': row[0],
                'name': row[1],
                'latitude': row[2],
                'longitude': row[3],
                'water_type': row[4],
                'cleanliness_level': row[5],
                'confidence_score': row[6],
                'notes': row[7],
                'timestamp': row[9]
            })
        
        conn.close()
        return jsonify(sources)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    # Initialize database
    init_db()
    
    print("🌊 Where's the Well? - Water Source Locator")
    print("=" * 50)
    print("Starting application...")
    print("Open your browser and go to: http://localhost:5000")
    print("\nFeatures:")
    print("• Interactive map with pin placement")
    print("• GPS location detection")
    print("• Photo-based water quality analysis")
    print("• Offline data storage")
    print("• Real-time statistics")
    print("\nTo use:")
    print("1. Click 'Find Me' to get your current location")
    print("2. Click anywhere on the map to place a water source")
    print("3. Fill in the details and upload a photo")
    print("4. The app will automatically analyze water quality")
    print("5. View all sources on the interactive map")
    
    # Run the Flask app
    app.run(debug=True, host='0.0.0.0', port=5000)
