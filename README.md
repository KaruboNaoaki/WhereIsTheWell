# Where's the Well?

An offline-first water source mapping application designed for underserved communities to locate, evaluate, and share information about local water sources.

## Overview

Where's the Well? helps communities build a collaborative database of water sources with built-in quality assessment. Using computer vision and community feedback, the app provides real-time water quality analysis and proximity-based recommendations - all while working completely offline.

## Features

- **Interactive Mapping**: Click-to-place water sources on an interactive map with GPS integration
- **Smart Water Analysis**: Automatic water quality assessment using image analysis (clean/muddy/contaminated)
- **Community Voting**: Upvote/downvote system for accuracy verification
- **Location-Based Search**: Find the nearest water sources sorted by distance
- **Offline Operation**: Works without internet connection after initial setup
- **Photo Documentation**: Capture and analyze water source images
- **User Attribution**: Track contributions with username system
- **Comments & Notes**: Community-driven additional information sharing

## Tech Stack

**Backend**: Python Flask with SQLite database  
**Frontend**: HTML5, CSS3, JavaScript with Tailwind CSS  
**Mapping**: Leaflet.js with OpenStreetMap tiles  
**Image Processing**: OpenCV and NumPy for water quality analysis  
**Storage**: Local SQLite database with browser LocalStorage for sessions

## Installation

### Prerequisites

Make sure you have Python 3.8 or higher installed on your system.

### Dependencies

Install the required Python packages:

```bash
pip install flask opencv-python numpy Pillow
```

### Running the Application

1. Clone or download the repository
2. Navigate to the project directory
3. Run the application:

```bash
python wheres_the_well_app.py
```

4. Open your browser and go to `http://localhost:5000`

## System Requirements

### Development Environment
- Python 3.8 or higher
- Modern web browser (Chrome, Firefox, Safari, or Edge)
- Camera access (optional, for photo capture)
- Location services (optional, for GPS features)

### Browser Compatibility
The application works on any modern browser that supports:
- HTML5 Geolocation API
- File API for image uploads
- ES6 JavaScript features
- CSS3 animations

## Usage

1. **Login**: Enter any username and password to get started (limited login for ease of testers, archived code can be used to re-enable)
2. **Find Your Location**: Click "Find Me" to center the map on your current location
3. **Add Water Sources**: Click anywhere on the map to place a new water source marker
4. **Upload Photos**: Take or upload photos for automatic water quality analysis
5. **Browse Nearby Sources**: Check the "Water Sources Near Me" panel for the closest options
6. **Community Feedback**: Vote on accuracy and leave comments on existing water sources

## Project Structure

The application consists of a single Python file containing:
- Flask web server and API endpoints
- SQLite database management
- OpenCV-based water quality classifier
- HTML template with embedded CSS and JavaScript
