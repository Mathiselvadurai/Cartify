import os
from app import create_app

app = create_app()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print("=" * 60)
    print(" Cartify: Smart Product Recommendation & E-Commerce System")
    print(" Powered by Oracle Database 26ai & Scikit-Learn TF-IDF")
    print(f" Web Server running on: http://127.0.0.1:{port}")
    print("=" * 60)
    app.run(debug=True, host="127.0.0.1", port=port)
