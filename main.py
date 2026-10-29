"""Android entry point (python-for-android 'webview' bootstrap): runs the app, the APK shows it in a WebView."""
from app import app

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False)
