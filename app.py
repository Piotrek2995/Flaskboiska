from flask import Flask, render_template, request, redirect, url_for, flash, abort, send_file
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, login_user, logout_user, login_required, current_user, UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
import os
import io

app = Flask(__name__)
app.secret_key = 'tajny_klucz'
# Użyj PostgreSQL na produkcji, SQLite lokalnie
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///users.db')
db = SQLAlchemy(app)

login_manager = LoginManager(app)
login_manager.login_view = 'login'

# MODELE
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False)
    password = db.Column(db.Text, nullable=False)


class Match(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(64))
    date = db.Column(db.String(32))
    time = db.Column(db.String(16))
    sport = db.Column(db.String(32))
    place = db.Column(db.String(128))
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))

class Report(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(128))
    description = db.Column(db.String(512))
    place = db.Column(db.String(128))
    date = db.Column(db.String(32))
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    photo = db.Column(db.LargeBinary)

class MatchSignup(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    match_id = db.Column(db.Integer, db.ForeignKey('match.id'))
    user = db.relationship('User', backref='signups')
    match = db.relationship('Match', backref='signups')

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Admin tylko dla admina
def admin_required(f):
    from functools import wraps
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or current_user.username != 'admin':
            return abort(403)
        return f(*args, **kwargs)
    return decorated_function

@app.route('/admin_users')
@admin_required
def admin_users():
    users = User.query.all()
    return (
        "<h2>Lista użytkowników:</h2>"
        "<table border='1' cellpadding='4'><tr><th>ID</th><th>Login</th><th>Hash hasła</th></tr>" +
        "".join(f"<tr><td>{u.id}</td><td>{u.username}</td><td style='font-size:10px'>{u.password}</td></tr>" for u in users) +
        "</table>"
    )

@app.route('/')
def index():
    matches = Match.query.order_by(Match.date, Match.time).all()
    reports = Report.query.order_by(Report.date.desc()).all()
    return render_template('index.html', matches=matches, reports=reports, user=current_user if current_user.is_authenticated else None)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        if User.query.filter_by(username=username).first():
            flash('Użytkownik już istnieje!')
            return redirect(url_for('register'))
        user = User(username=username, password=generate_password_hash(password))
        db.session.add(user)
        db.session.commit()
        flash('Rejestracja udana! Możesz się zalogować.')
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter_by(username=username).first()
        if user and check_password_hash(user.password, password):
            login_user(user)
            return redirect(url_for('index'))
        flash('Nieprawidłowe dane logowania.')
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))

@app.route('/add_match', methods=['POST'])
@login_required
def add_match():
    m = Match(
        name=current_user.username,
        date=request.form['date'],
        time=request.form['time'],
        sport=request.form['sport'],
        place=request.form['place'],
        user_id=current_user.id
    )
    db.session.add(m)
    db.session.commit()
    flash('Dodano spotkanie.')
    return redirect(url_for('index'))

@app.route('/report_issue', methods=['POST'])
@login_required
def report_issue():
    photo_file = request.files.get('photo')
    photo_data = photo_file.read() if photo_file and photo_file.filename else None
    r = Report(
        title=request.form['title'],
        description=request.form['description'],
        place=request.form['place'],
        date=request.form['date'],
        photo=photo_data,
        user_id=current_user.id
    )
    db.session.add(r)
    db.session.commit()
    flash('Zgłoszono awarię.')
    return redirect(url_for('index'))

@app.route('/join_match/<int:match_id>', methods=['POST'])
@login_required
def join_match(match_id):
    existing = MatchSignup.query.filter_by(user_id=current_user.id, match_id=match_id).first()
    if not existing:
        signup = MatchSignup(user_id=current_user.id, match_id=match_id)
        db.session.add(signup)
        db.session.commit()
        flash('Dołączono do spotkania!')
    else:
        flash('Już jesteś zapisany na to spotkanie.')
    return redirect(url_for('index'))

@app.route('/spotkania')
def meetings():
    matches = Match.query.order_by(Match.date, Match.time).all()
    user = current_user if current_user.is_authenticated else None
    return render_template('meetings.html', matches=matches, user=user)

@app.route('/awarie')
def issues():
    reports = Report.query.order_by(Report.date.desc()).all()
    user = current_user if current_user.is_authenticated else None
    return render_template('issues.html', reports=reports, user=user)


@app.route('/report_photo/<int:report_id>')
def report_photo(report_id):
    report = Report.query.get(report_id)
    if report and report.photo:
        return send_file(io.BytesIO(report.photo), mimetype='image/jpeg')
    return '', 404

# Dodaj użytkowników jeśli nie istnieją (raz, przy starcie)
def ensure_default_users():
    default_users = [
        {'username': 'admin', 'password': 'admin123'},
        {'username': 'jan',   'password': 'janek'},
        {'username': 'ola',   'password': 'olcia'},
        {'username': 'test',  'password': 'test'}
    ]
    for u in default_users:
        if not User.query.filter_by(username=u['username']).first():
            user = User(username=u['username'], password=generate_password_hash(u['password']))
            db.session.add(user)
    db.session.commit()

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        ensure_default_users()
    app.run(debug=True)
else:
    with app.app_context():
        db.create_all()
        ensure_default_users()

