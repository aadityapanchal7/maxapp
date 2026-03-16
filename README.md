# Max App - Premium Lookmaxxing Platform

A comprehensive facial analysis and self-improvement platform with mobile app, backend API, and AI-powered facial analysis service.

## 🏗️ Architecture

- **Backend API** (FastAPI + MongoDB) - Main application server
- **Facial Analysis Service** (FastAPI + MediaPipe) - AI-powered facial analysis
- **Mobile App** (React Native/Expo) - Cross-platform mobile application

## 🚀 Quick Start

### Prerequisites

- Python 3.8+
- Node.js 16+
- MongoDB
- Expo CLI
- Android Studio/iOS Xcode (for mobile development)

### 1. Clone & Setup

```bash
git clone <repository-url>
cd cannon
```

### 2. Backend API Setup

```bash
cd backend

# Create virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Create .env file (copy from example)
cp .env.example .env
# Edit .env with your configuration


# Run the API server
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

Backend runs on `http://localhost:8000`

### 3. Facial Analysis Service Setup

```bash
cd cannon_facial_analysis

# Create virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Create .env file
cp .env.example .env
# Add your GROQ API key to .env

uvicorn app.main:app --host 0.0.0.0 --port 8001 --reload
```

Facial analysis service runs on `http://localhost:8001`

### 4. Mobile App Setup

```bash
cd mobile

# Install dependencies
npm install

# Start Expo development server
npm start

# For Android
npm run android

# For iOS
npm run ios

# For web
npm run web
```

**note**
**make sure the laptop is connected to the same network as the mobile device**


## 📊 Services & Ports

| Service | Port | Description |
|---------|------|-------------|
| Backend API | 8000 | Main FastAPI application |
| Facial Analysis | 8001 | AI facial analysis service |

| Mobile Dev Server | 8081 | Expo development server |
