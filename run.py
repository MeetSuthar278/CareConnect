import os

from app import create_app

app = create_app()

if __name__ == "__main__":
    app.run(debug=not app.config['HOSTED_MODE'] and os.getenv('FLASK_DEBUG') == '1')
