"""
Sustaining Audit - Full Flask app with PWA support
Features:
- Home page
- Checklist add/edit
- New Audit with Score buttons (0-3)
- Photo capture upload
- localStorage form retention
- Delete Audit
- MIL export
- Audit category scores + total
- Audit export to Excel
- PWA support: manifest.json + service worker + add to home screen
Compatible with Flask 3.x and Python 3.12+
"""
from flask import Flask, request, redirect, url_for, render_template_string, send_file, flash
from werkzeug.utils import secure_filename
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import os
import pandas as pd

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'uploads')
STATIC_FOLDER = os.path.join(BASE_DIR, 'static')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(STATIC_FOLDER, exist_ok=True)

app = Flask(__name__)
app.secret_key = 'dev-secret'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(BASE_DIR, 'audit.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

db = SQLAlchemy(app)

# ---- Models ----
class Category(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False, unique=True)

class ChecklistItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    category_id = db.Column(db.Integer, db.ForeignKey('category.id'))
    category = db.relationship('Category', backref='items')
    text = db.Column(db.String(500), nullable=False)
    original_spec = db.Column(db.Text, nullable=True)

class Audit(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    vendor = db.Column(db.String(200), nullable=False)
    audit_date = db.Column(db.Date, nullable=False)
    audit_area = db.Column(db.String(200), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class AuditItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    audit_id = db.Column(db.Integer, db.ForeignKey('audit.id'))
    audit = db.relationship('Audit', backref='audit_items')
    checklist_item_id = db.Column(db.Integer, db.ForeignKey('checklist_item.id'))
    checklist_item = db.relationship('ChecklistItem')
    score = db.Column(db.Integer, nullable=True)
    record = db.Column(db.Text, nullable=True)
    photo_filename = db.Column(db.String(300), nullable=True)

# ---- DB init ----
with app.app_context():
    db.create_all()

# ---- Base Template ----
BASE_TEMPLATE = '''
<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Sustaining Audit</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <link rel="manifest" href="/static/manifest.json">
    <script>
      if('serviceWorker' in navigator){
        navigator.serviceWorker.register('/static/service-worker.js')
        .then(function(){ console.log('Service Worker registered'); })
        .catch(function(err){ console.log('Service Worker failed', err); });
      }
    </script>
    <style>
      body { background: #f5f8fb; }
      .score-btn { margin-right: 5px; }
      .score-selected { background-color: #0d6efd; color: white; }
    </style>
  </head>
  <body class="p-4">
    <div class="container">
      <div class="d-flex justify-content-between align-items-center mb-3">
        <h1 class="h3">Sustaining Audit</h1>
        <div>
          <a class="btn btn-light" href="/">Home</a>
          <a class="btn btn-primary" href="/checklist">Checklist</a>
          <a class="btn btn-primary" href="/audits">Audits</a>
          <a class="btn btn-outline-primary" href="/audits/new">New Audit</a>
          <a class="btn btn-outline-primary" href="/export_mil">Export MIL (Excel)</a>
        </div>
      </div>
      {% with messages = get_flashed_messages() %}
        {% if messages %}
          {% for m in messages %}
            <div class="alert alert-info">{{ m }}</div>
          {% endfor %}
        {% endif %}
      {% endwith %}
      {{ content|safe }}
    </div>
    <script>
      function selectScore(itemId, score) {
          const buttons = document.querySelectorAll(`.score-btn[data-item='${itemId}']`);
          buttons.forEach(btn => btn.classList.remove('score-selected'));
          document.querySelector(`#score_${itemId}_${score}`).classList.add('score-selected');
          document.querySelector(`#score_input_${itemId}`).value = score;
      }

      const form = document.querySelector('form');
      if (form) {
          const storageKey = 'new_audit_form';
          const saved = localStorage.getItem(storageKey);
          if(saved){
              const data = JSON.parse(saved);
              for(const key in data){
                  const el = document.querySelector(`[name='${key}']`);
                  if(el && el.type !== 'file') el.value = data[key];
              }
          }
          form.addEventListener('input', ()=>{
              const data = {};
              form.querySelectorAll('input, textarea, select').forEach(el=>{
                  if(el.type !== 'file') data[el.name] = el.value;
              });
              localStorage.setItem(storageKey, JSON.stringify(data));
          });
          form.addEventListener('submit', ()=>{
              localStorage.removeItem(storageKey);
          });
      }
    </script>
  </body>
</html>
'''

# ---- Home ----
@app.route('/')
def home():
    content = '''
    <div class="text-center mt-5">
        <h2>Welcome to Sustaining Audit</h2>
        <p>Use the navigation buttons above to manage Checklist, Audits, or export MIL.</p>
        <a class="btn btn-primary mt-3" href="/audits">Go to Audits</a>
        <a class="btn btn-secondary mt-3 ms-2" href="/checklist">Go to Checklist</a>
        <a class="btn btn-success mt-3 ms-2" href="/audits/new">Create New Audit</a>
    </div>
    '''
    return render_template_string(BASE_TEMPLATE, content=content)

# ---- Checklist ----
@app.route('/checklist', methods=['GET','POST'])
def checklist():
    if request.method=='POST':
        if 'category_name' in request.form:
            name = request.form['category_name'].strip()
            if name and not Category.query.filter_by(name=name).first():
                db.session.add(Category(name=name))
                db.session.commit()
                flash('Category added')
            else:
                flash('Category exists or empty')
            return redirect('/checklist')
        elif 'item_id' in request.form:
            item = ChecklistItem.query.get(int(request.form['item_id']))
            item.text = request.form['item_text']
            item.original_spec = request.form.get('original_spec','')
            db.session.commit()
            flash('Checklist item updated')
            return redirect('/checklist')
        elif 'item_text' in request.form:
            category_id = int(request.form['category_id'])
            text = request.form['item_text'].strip()
            original_spec = request.form.get('original_spec','').strip()
            if text:
                db.session.add(ChecklistItem(category_id=category_id, text=text, original_spec=original_spec))
                db.session.commit()
                flash('Checklist item added')
            return redirect('/checklist')
    categories = Category.query.order_by(Category.name).all()
    items = ChecklistItem.query.order_by(ChecklistItem.id).all()
    content = "<h4>Add Category</h4><form method='post'><input name='category_name' class='form-control mb-2' placeholder='Category Name' required><button class='btn btn-primary mb-3'>Add Category</button></form>"
    content += "<h4>Add Checklist Item</h4><form method='post'><select name='category_id' class='form-select mb-2' required>"
    for c in categories:
        content += f"<option value='{c.id}'>{c.name}</option>"
    content += "</select><input name='item_text' class='form-control mb-2' placeholder='Checklist Item Text' required>"
    content += "<input name='original_spec' class='form-control mb-2' placeholder='Original Spec (optional)'>"
    content += "<button class='btn btn-primary mb-3'>Add Checklist Item</button></form><h4>Existing Checklist Items</h4>"
    for i in items:
        content += f"<form method='post' class='mb-2 border p-2 rounded'><input type='hidden' name='item_id' value='{i.id}'>"
        content += f"<input name='item_text' class='form-control mb-1' value='{i.text}' required>"
        content += f"<input name='original_spec' class='form-control mb-1' value='{i.original_spec or ''}'>"
        content += "<button class='btn btn-sm btn-success'>Save</button></form>"
    return render_template_string(BASE_TEMPLATE, content=content)

# ---- Audits List ----
@app.route('/audits')
def audits_list():
    audits = Audit.query.order_by(Audit.audit_date.desc()).all()
    content = "<div class='d-flex justify-content-between align-items-center'><h4>Audits</h4>"
    content += "<a class='btn btn-primary' href='/audits/new'>New Audit</a></div><ul class='mt-3'>"
    for a in audits:
        category_scores = {}
        total_score = 0
        total_items = 0
        for ai in a.audit_items:
            cat = ai.checklist_item.category.name
            if cat not in category_scores: category_scores[cat] = {'sum':0,'count':0}
            if ai.score is not None: category_scores[cat]['sum'] += ai.score
            category_scores[cat]['count'] += 1
            if ai.score is not None: total_score += ai.score
            total_items +=1
        content += f"<li><strong>{a.vendor} - {a.audit_date} - {a.audit_area}</strong>"
        content += f" <a href='/audits/delete/{a.id}' class='btn btn-sm btn-danger ms-2'>Delete</a>"
        content += f" <a href='/audits/export/{a.id}' class='btn btn-sm btn-success ms-1'>Export Excel</a><br>"
        for cat, sc in category_scores.items():
            pct = (sc['sum'] / (sc['count']*3)*100) if sc['count'] else 0
            content += f"<small>{cat}: {pct:.1f}%</small> &nbsp;"
        total_pct = (total_score/(total_items*3)*100) if total_items else 0
        content += f"<small>Total: {total_pct:.1f}%</small></li>"
    content += "</ul>"
    return render_template_string(BASE_TEMPLATE, content=content)

# ---- New Audit ----
@app.route('/audits/new', methods=['GET','POST'])
def new_audit():
    categories = Category.query.order_by(Category.name).all()
    items = ChecklistItem.query.order_by(ChecklistItem.id).all()
    if request.method=='POST':
        vendor = request.form['vendor']
        audit_date = datetime.fromisoformat(request.form['audit_date']).date()
        audit_area = request.form['audit_area']
        audit = Audit(vendor=vendor, audit_date=audit_date, audit_area=audit_area)
        db.session.add(audit)
        db.session.commit()
        for item in items:
            score = request.form.get(f'score_{item.id}')
            record = request.form.get(f'record_{item.id}')
            photo = request.files.get(f'photo_{item.id}')
            filename = None
            if photo and photo.filename:
                filename = secure_filename(f"{audit.id}_{item.id}_{photo.filename}")
                photo.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            audit_item = AuditItem(audit_id=audit.id, checklist_item_id=item.id,
                                   score=int(score) if score else None,
                                   record=record, photo_filename=filename)
            db.session.add(audit_item)
        db.session.commit()
        flash('Audit created successfully!')
        return redirect(url_for('audits_list'))

    content = "<h4>Create New Audit</h4><form method='post' enctype='multipart/form-data'>"
    content += "<input name='vendor' class='form-control mb-2' placeholder='Vendor' required>"
    content += "<input type='date' name='audit_date' class='form-control mb-2' required>"
    content += "<input name='audit_area' class='form-control mb-2' placeholder='Audit Area' required>"
    content += "<h5>Checklist Items</h5>"
    for i in items:
        content += f"<div class='mb-3 border p-2 rounded'><strong>{i.text} ({i.category.name})</strong><br>"
        content += f"Score: <input type='hidden' name='score_{i.id}' id='score_input_{i.id}'>"
        for s in range(4):
            content += f"<button type='button' class='btn btn-outline-primary score-btn' id='score_{i.id}_{s}' data-item='{i.id}' onclick='selectScore({i.id},{s})'>{s}</button>"
        content += f"<br>Record/Comments: <input type='text' name='record_{i.id}' class='form-control mb-1'>"
        content += f"Photo: <input type='file' name='photo_{i.id}' class='form-control' accept='image/*' capture></div>"
    content += "<button class='btn btn-primary'>Create Audit</button></form>"
    return render_template_string(BASE_TEMPLATE, content=content)

# ---- Delete Audit ----
@app.route('/audits/delete/<int:audit_id>')
def delete_audit(audit_id):
    audit = Audit.query.get_or_404(audit_id)
    for ai in audit.audit_items:
        if ai.photo_filename:
            try: os.remove(os.path.join(app.config['UPLOAD_FOLDER'], ai.photo_filename))
            except: pass
        db.session.delete(ai)
    db.session.delete(audit)
    db.session.commit()
    flash('Audit deleted successfully.')
    return redirect(url_for('audits_list'))

# ---- Export Audit Excel ----
@app.route('/audits/export/<int:audit_id>')
def export_audit(audit_id):
    audit = Audit.query.get_or_404(audit_id)
    rows = []
    for idx, ai in enumerate(audit.audit_items, start=1):
        rows.append({'No': idx,
                     'Category': ai.checklist_item.category.name,
                     'Checking Item': ai.checklist_item.text,
                     'Score': ai.score,
                     'Record': ai.record or '',
                     'Vendor': audit.vendor,
                     'Audit Date': audit.audit_date,
                     'Audit Area': audit.audit_area})
    df = pd.DataFrame(rows)
    out_path = os.path.join(BASE_DIR, f'audit_{audit.id}_{datetime.utcnow().strftime("%Y%m%d%H%M%S")}.xlsx')
    df.to_excel(out_path, index=False)
    return send_file(out_path, as_attachment=True)

# ---- MIL Export ----
@app.route('/export_mil')
def export_mil():
    rows=[]
    q = AuditItem.query.filter(AuditItem.score!=3).order_by(AuditItem.id).all()
    for idx, ai in enumerate(q,start=1):
        rows.append({'No':idx,
                     'Checking item':ai.checklist_item.text,
                     'Category':ai.checklist_item.category.name,
                     'Record':ai.record or '',
                     'Status':'Open' if ai.score is None or ai.score<3 else 'Closed',
                     'Action':'',
                     'Vendor DRI':ai.audit.vendor,
                     'Due Date':'',
                     'Closed date':'',
                     'Remark':''})
    if not rows:
        flash('No MIL items.')
        return redirect('/')
    df = pd.DataFrame(rows)
    out_path = os.path.join(BASE_DIR,f'mil_export_{datetime.utcnow().strftime("%Y%m%d%H%M%S")}.xlsx')
    df.to_excel(out_path,index=False)
    return send_file(out_path,as_attachment=True)

if __name__=='__main__':
    app.run(debug=True)
