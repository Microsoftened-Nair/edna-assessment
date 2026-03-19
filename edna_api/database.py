import os
from datetime import datetime
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), default='researcher')

class Run(db.Model):
    __tablename__ = 'runs'
    id = db.Column(db.Integer, primary_key=True)
    sample_id = db.Column(db.String(100), unique=True, nullable=False)
    input_type = db.Column(db.String(20), nullable=False)
    input_files = db.Column(db.JSON, nullable=False)
    output_dir = db.Column(db.String(255), nullable=False)
    start_time = db.Column(db.String(50), nullable=False)
    end_time = db.Column(db.String(50), nullable=True)
    status = db.Column(db.String(20), nullable=False, default='queued')
    success = db.Column(db.Boolean, nullable=True)
    processing_time = db.Column(db.Float, nullable=True)
    pipeline_steps = db.Column(db.JSON, nullable=True)
    error = db.Column(db.Text, nullable=True)
    batch_id = db.Column(db.String(100), nullable=True)

class Batch(db.Model):
    __tablename__ = 'batches'
    id = db.Column(db.Integer, primary_key=True)
    batch_id = db.Column(db.String(100), unique=True, nullable=False)
    status = db.Column(db.String(20), nullable=False, default='queued')
    total_samples = db.Column(db.Integer, default=0)
    successful_samples = db.Column(db.Integer, default=0)
    failed_samples = db.Column(db.Integer, default=0)
    start_time = db.Column(db.String(50), nullable=False)
    end_time = db.Column(db.String(50), nullable=True)
    total_processing_time = db.Column(db.Float, nullable=True)
    summary_report = db.Column(db.JSON, nullable=True)

def init_db(app):
    database_uri = os.environ.get('DATABASE_URL', 'sqlite:///edna.db')
    app.config['SQLALCHEMY_DATABASE_URI'] = database_uri
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    
    db.init_app(app)
    
    with app.app_context():
        db.create_all()
        # Create a default admin user if no users exist
        if User.query.count() == 0:
            from werkzeug.security import generate_password_hash
            default_admin = User(
                username='admin',
                password_hash=generate_password_hash('password123'),
                role='admin'
            )
            db.session.add(default_admin)
            db.session.commit()
