"""
Infinity Travels - Flask version
Run:   pip install flask
       python app.py
Open:  http://127.0.0.1:5000
Bookings are stored in a SQLite database (bookings.db by default).
View them at /admin (set ADMIN_PASSWORD first).

Environment variables:
  ADMIN_PASSWORD  password for /admin (admin is disabled if unset)
  DATABASE_PATH   where to keep the SQLite file (default: next to app.py)
  FLASK_DEBUG     set to 1 for local debugging only

Email (optional - if SMTP_* are not set, bookings still work, no email is sent):
  SMTP_HOST       e.g. smtp.gmail.com
  SMTP_PORT       587 (STARTTLS, default) or 465 (SSL)
  SMTP_USER       your SMTP login, e.g. yourname@gmail.com
  SMTP_PASSWORD   for Gmail use an App Password, not your normal password
  MAIL_FROM       sender shown to customers (default: SMTP_USER)
  OWNER_EMAIL     where you get a "new booking" alert (optional)
"""
import hmac
import logging
import os
import random
import re
import smtplib
import sqlite3
import ssl
import threading
from datetime import date, datetime
from email.message import EmailMessage
from html import escape
from pathlib import Path

from flask import Flask, Response, jsonify, render_template_string, request

app = Flask(__name__)
DB_FILE = os.environ.get("DATABASE_PATH") or str(Path(__file__).with_name("bookings.db"))
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "")

SMTP_HOST = os.environ.get("SMTP_HOST", "")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USER = os.environ.get("SMTP_USER", "")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")
MAIL_FROM = os.environ.get("MAIL_FROM") or SMTP_USER
OWNER_EMAIL = os.environ.get("OWNER_EMAIL", "")
EMAIL_ENABLED = bool(SMTP_HOST and SMTP_USER and SMTP_PASSWORD and MAIL_FROM)

log = logging.getLogger("infinity")
logging.basicConfig(level=logging.INFO)


def get_db():
    con = sqlite3.connect(DB_FILE, timeout=10)
    con.execute(
        """CREATE TABLE IF NOT EXISTS bookings (
               id TEXT PRIMARY KEY, created_at TEXT, name TEXT, email TEXT,
               phone TEXT, package TEXT, travel_date TEXT, persons INTEGER, total INTEGER)"""
    )
    return con

# ----------------------------------------------------------------- DATA
PACKAGES = [
    dict(name="Paris City of Love", loc="Paris, France", dur="7 Days", price=100000, css="c-paris",
         tags=["🏨 Hotel", "✈️ Flight", "🗺️ Sightseeing"],
         img="https://i.pinimg.com/736x/4a/b8/a5/4ab8a52ec69e971d00f94c0d0c45ad76.jpg"),
    dict(name="Maldives Island Escape", loc="Maldives", dur="4N/5D", price=80000, css="c-maldives",
         tags=["🏨 Resort", "🤿 Snorkeling", "🍽️ Meals"],
         img="https://i.pinimg.com/736x/14/1d/f7/141df716ab8e751b9d7b9015cf72211c.jpg"),
    dict(name="Dubai Desert Glamour", loc="Dubai, UAE", dur="4N/5D", price=100000, css="c-dubai",
         tags=["🏨 Hotel", "🐪 Desert Safari", "✈️ Flight"],
         img="https://i.pinimg.com/1200x/64/0e/c3/640ec39a093f78068ce041dd95b03a16.jpg"),
    dict(name="Kerala Backwaters Bliss", loc="Kerala, India", dur="4N/5D", price=25000, css="c-kerala",
         tags=["🛶 Houseboat", "🌿 Nature", "🍽️ Meals"],
         img="https://i.pinimg.com/736x/31/bc/84/31bc84e0fa95c63cffe8a77f39d3e894.jpg"),
    dict(name="Goa Beach Party", loc="Goa, India", dur="4N/5D", price=20000, css="c-goa",
         tags=["🏨 Hotel", "🚌 Transport", "🏄 Water Sports"],
         img="https://i.pinimg.com/1200x/e9/87/9e/e9879e7e5dc741625e9016bda1d80182.jpg"),
    dict(name="Hyderabad Heritage Tour", loc="Hyderabad, India", dur="3N/4D", price=25000, css="c-hyd",
         tags=["🏨 Hotel", "🍛 Biryani Trail", "🗺️ Sightseeing"],
         img="https://i.pinimg.com/1200x/38/9e/2b/389e2b5dbd406338f6d48d7892849c34.jpg"),
    dict(name="Mumbai City Lights", loc="Mumbai, India", dur="2N/3D", price=5500, css="c-mumbai",
         tags=["🏨 Hotel", "🚌 Transport", "🎭 Bollywood"],
         img="https://i.pinimg.com/736x/2e/13/2e/2e132e59000aa4d018ec74e2dd06266c.jpg"),
    dict(name="Pune Hills Getaway", loc="Pune, India", dur="3N/4D", price=12000, css="c-pune",
         tags=["🏨 Hotel", "🌄 Forts", "🚌 Transport"],
         img="https://i.pinimg.com/736x/5e/0a/d4/5e0ad4dc950fe58ed26b1d930009d776.jpg"),
    dict(name="Delhi Capital Explorer", loc="Delhi, India", dur="2N/3D", price=18000, css="c-delhi",
         tags=["🏨 Hotel", "🕌 Heritage", "🍢 Street Food"],
         img="https://i.pinimg.com/736x/b6/55/dc/b655dcdfe59835357a93dd30ca070c0a.jpg"),
    dict(name="Tirupati Divine Darshan", loc="Tirupati, Andhra Pradesh", dur="2N/3D", price=17000, css="c-tirupati",
         tags=["🏨 Hotel", "🚌 Transport", "🎟️ VIP Darshan"],
         img="https://i.pinimg.com/736x/8d/1b/09/8d1b094207422a63b790f727277e64c5.jpg"),
    dict(name="Ladakh Mountain Odyssey", loc="Leh, Nubra, Pangong", dur="4N/5D", price=58000, css="c-ladakh",
         tags=["⛺ Camping", "🏍️ Bike Ride", "🌌 Stargazing"],
         img="https://i.pinimg.com/736x/55/1b/bc/551bbc813cc826ee7f72d6ca58ec9b3b.jpg"),
    dict(name="Manali Snow Adventure", loc="Manali, Himachal Pradesh", dur="7 Days", price=40000, css="c-manali",
         tags=["🏨 Hotel", "⛷️ Snow Sports", "🚌 Transport"],
         img="https://i.pinimg.com/736x/5c/7e/10/5c7e10037f1c91aee7dba92ac780b897.jpg"),
    dict(name="Rajasthan Royal Retreat", loc="Jaipur · Jodhpur · Udaipur", dur="7 Days", price=60000, css="c-rajasthan",
         tags=["🏯 Heritage Hotel", "🐪 Camel Safari", "🎨 Culture"],
         img="https://i.pinimg.com/736x/60/13/e4/6013e43e69955c724d78cad528ced1fd.jpg"),
    dict(name="Bangkok Exotic Getaway", loc="Bangkok, Thailand", dur="4N/5D", price=69000, css="c-bangkok",
         tags=["🏨 Hotel", "✈️ Flight", "🌃 Nightlife"],
         img="https://i.pinimg.com/736x/87/26/b8/8726b87b7aa340690eff70bfd0874a5d.jpg"),
]

DAY_TRIPS = [
    dict(name="Pune City Darshan", loc="Pune · 1 Day Trip", dur="", price=1100, css="c-pune",
         tags=["🚌 AC Bus", "🗺️ Guided Tour"],
         img="https://i.pinimg.com/736x/5e/0a/d4/5e0ad4dc950fe58ed26b1d930009d776.jpg"),
    dict(name="Mumbai City Darshan", loc="Mumbai · 1 Day Trip", dur="", price=1300, css="c-mumbai",
         tags=["🚌 AC Bus", "🗺️ Guided Tour"],
         img="https://i.pinimg.com/736x/2e/13/2e/2e132e59000aa4d018ec74e2dd06266c.jpg"),
]

# server-side source of truth for prices (never trust the browser's price)
PRICE_BY_NAME = {p["name"]: p["price"] for p in PACKAGES + DAY_TRIPS}


def inr(n) -> str:
    """Format a number with Indian digit grouping: 100000 -> 1,00,000"""
    s = str(int(n))
    if len(s) <= 3:
        return s
    head, tail = s[:-3], s[-3:]
    groups = []
    while len(head) > 2:
        groups.insert(0, head[-2:])
        head = head[:-2]
    if head:
        groups.insert(0, head)
    return ",".join(groups + [tail])


app.jinja_env.filters["inr"] = inr

# ------------------------------------------------------------- TEMPLATE
PAGE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Infinity Travels — Your Journey Begins Here</title>
<link href="https://fonts.googleapis.com/css2?family=Playfair+Display:wght@700;900&family=DM+Sans:wght@300;400;500;600&display=swap" rel="stylesheet">
<style>
  :root { --gold:#C8922A; --gold-light:#E8B94F; --terra:#C4613A; --deep:#1A1208; --cream:#FBF7EE; --sand:#F5EFE0; }
  * { margin:0; padding:0; box-sizing:border-box; }
  html { scroll-behavior:smooth; }
  body { font-family:'DM Sans',sans-serif; background:var(--cream); color:var(--deep); }

  nav { position:fixed; top:0; left:0; right:0; z-index:100; display:flex; align-items:center;
        justify-content:space-between; padding:1rem 3rem; background:rgba(26,18,8,.95); backdrop-filter:blur(10px); }
  .logo { font-family:'Playfair Display',serif; font-size:1.5rem; color:var(--gold-light); }
  .logo span { color:var(--terra); }
  nav ul { display:flex; gap:2rem; list-style:none; }
  nav ul a { color:#F5EFE0; text-decoration:none; font-size:.9rem; font-weight:500; transition:color .2s; }
  nav ul a:hover { color:var(--gold-light); }

  .hero { min-height:100vh;
    background:linear-gradient(rgba(15,10,5,.62),rgba(20,13,5,.70)),
      url('https://images.unsplash.com/photo-1469854523086-cc02fe5d8800?w=1600&auto=format&fit=crop') center/cover no-repeat;
    display:flex; flex-direction:column; justify-content:center; align-items:center; text-align:center; padding:6rem 2rem 3rem; }
  .hero-badge { background:var(--terra); color:#fff; padding:.4rem 1.2rem; border-radius:30px; font-size:.75rem;
    font-weight:600; letter-spacing:2px; text-transform:uppercase; margin-bottom:1.5rem; }
  .hero h1 { font-family:'Playfair Display',serif; font-size:clamp(2.5rem,6vw,5rem); color:var(--sand); line-height:1.1; margin-bottom:1rem; }
  .hero h1 span { color:var(--gold-light); }
  .hero p { color:#A89880; font-size:1.1rem; max-width:500px; margin-bottom:2.5rem; line-height:1.6; }
  .hero-btn { background:var(--gold); color:var(--deep); padding:1rem 2.5rem; border-radius:50px; font-size:1rem;
    font-weight:700; text-decoration:none; display:inline-block; transition:all .2s; }
  .hero-btn:hover { background:var(--gold-light); transform:translateY(-2px); }

  .packages { padding:5rem 3rem; background:var(--cream); }
  .day-trips { padding:5rem 3rem; background:var(--sand); }
  .section-title { text-align:center; margin-bottom:3rem; }
  .section-title h2 { font-family:'Playfair Display',serif; font-size:2.5rem; margin-bottom:.5rem; }
  .section-title p { color:#6B5B45; }
  .section-tag { display:inline-block; background:var(--terra); color:#fff; padding:.3rem 1rem; border-radius:30px;
    font-size:.72rem; font-weight:600; letter-spacing:2px; text-transform:uppercase; margin-bottom:.8rem; }

  .cards { display:grid; grid-template-columns:repeat(auto-fit,minmax(270px,1fr)); gap:1.5rem; max-width:1200px; margin:0 auto; }
  .cards.day { max-width:600px; }
  .card { background:#fff; border-radius:16px; overflow:hidden; box-shadow:0 4px 20px rgba(26,18,8,.08);
    transition:transform .3s,box-shadow .3s; cursor:pointer; border:2px solid transparent; }
  .card:hover { transform:translateY(-6px); box-shadow:0 12px 40px rgba(26,18,8,.15); }
  .card.selected { border-color:var(--gold); }
  .card-img { height:160px; position:relative; }
  .card-img img { width:100%; height:100%; object-fit:cover; display:block; }
  .badge-days { position:absolute; top:10px; right:10px; background:rgba(0,0,0,.55); color:#fff;
    padding:.3rem .7rem; border-radius:20px; font-size:.72rem; font-weight:600; }
  .card-body { padding:1.2rem; }
  .card-body h3 { font-family:'Playfair Display',serif; font-size:1.15rem; margin-bottom:.25rem; }
  .location { color:#6B5B45; font-size:.82rem; margin-bottom:.7rem; }
  .card-features { display:flex; gap:.4rem; flex-wrap:wrap; margin-bottom:1rem; }
  .feature-tag { background:var(--sand); padding:.2rem .55rem; border-radius:20px; font-size:.7rem; font-weight:500; }
  .card-footer { display:flex; align-items:center; justify-content:space-between; }
  .price { font-size:1.25rem; font-weight:700; color:var(--gold); }
  .price span { font-size:.72rem; color:#6B5B45; font-weight:400; }
  .select-btn { background:var(--deep); color:#fff; border:none; padding:.5rem 1.1rem; border-radius:25px;
    font-size:.82rem; font-weight:600; cursor:pointer; transition:background .2s; }
  .select-btn:hover, .card.selected .select-btn { background:var(--gold); color:var(--deep); }

  .booking-section { padding:5rem 3rem; background:linear-gradient(135deg,#1A1208,#2D1E0A); }
  .booking-section .section-title h2 { color:var(--sand); }
  .booking-section .section-title p { color:#A89880; }
  .form-container { max-width:650px; margin:0 auto; background:rgba(255,255,255,.05);
    border:1px solid rgba(200,146,42,.3); border-radius:20px; padding:2.5rem; }
  .selected-package-display { background:rgba(200,146,42,.15); border:1px solid var(--gold); border-radius:12px;
    padding:1rem 1.5rem; margin-bottom:2rem; display:none; }
  .selected-package-display.show { display:block; }
  .selected-package-display h4 { color:var(--gold-light); font-size:.8rem; letter-spacing:1px; text-transform:uppercase; }
  .selected-package-display p { color:var(--sand); font-size:1.1rem; font-weight:600; margin-top:.2rem; }
  .form-row { display:grid; grid-template-columns:1fr 1fr; gap:1rem; margin-bottom:1rem; }
  .form-group { display:flex; flex-direction:column; margin-bottom:1rem; }
  .form-group label { color:#A89880; font-size:.82rem; font-weight:600; letter-spacing:.5px; margin-bottom:.4rem; text-transform:uppercase; }
  .form-group input, .form-group select { background:rgba(255,255,255,.08); border:1px solid rgba(200,146,42,.25);
    color:var(--sand); padding:.85rem 1rem; border-radius:10px; font-size:.95rem; font-family:inherit; outline:none; }
  .form-group input:focus, .form-group select:focus { border-color:var(--gold); }
  .form-group select option { background:#2D1E0A; color:var(--sand); }
  .form-group input::placeholder { color:#5A4A35; }
  .total-price { background:rgba(200,146,42,.1); border:1px dashed rgba(200,146,42,.4); border-radius:10px;
    padding:1rem 1.5rem; display:flex; justify-content:space-between; align-items:center; margin-bottom:1.5rem; }
  .total-price span { color:#A89880; font-size:.9rem; }
  .total-price strong { color:var(--gold-light); font-size:1.4rem; }
  .error { color:#ff9c80; font-size:.88rem; min-height:1.2rem; margin-bottom:.8rem; }
  .book-btn { width:100%; background:var(--gold); color:var(--deep); border:none; padding:1.1rem; border-radius:12px;
    font-size:1rem; font-weight:700; cursor:pointer; font-family:inherit; transition:all .2s; }
  .book-btn:hover { background:var(--gold-light); transform:translateY(-1px); }
  .book-btn:disabled { opacity:.6; cursor:wait; }

  .modal-overlay { position:fixed; inset:0; z-index:999; background:rgba(0,0,0,.85); backdrop-filter:blur(5px);
    display:none; align-items:center; justify-content:center; padding:2rem; }
  .modal-overlay.show { display:flex; }
  .modal { background:#fff; border-radius:24px; padding:3rem; text-align:center; max-width:480px; width:100%;
    animation:popIn .4s cubic-bezier(.34,1.56,.64,1); }
  @keyframes popIn { from { transform:scale(.7); opacity:0; } to { transform:scale(1); opacity:1; } }
  .modal-icon { font-size:4rem; margin-bottom:1rem; }
  .modal h2 { font-family:'Playfair Display',serif; font-size:1.8rem; margin-bottom:.5rem; }
  .modal p.lead { color:#6B5B45; line-height:1.6; margin-bottom:1.5rem; }
  .booking-id { background:var(--sand); border-radius:12px; padding:1rem; margin-bottom:1.5rem; }
  .booking-id span { display:block; font-size:.75rem; color:#6B5B45; text-transform:uppercase; letter-spacing:1px; }
  .booking-id strong { font-size:1.3rem; color:var(--gold); letter-spacing:3px; }
  .modal-details { text-align:left; background:var(--sand); border-radius:12px; padding:1rem 1.5rem; margin-bottom:1.5rem; }
  .modal-details p { font-size:.88rem; padding:.3rem 0; border-bottom:1px solid #E8DFD0; }
  .modal-details p:last-child { border-bottom:none; }
  .modal-details strong { color:var(--gold); }
  .modal-close { background:var(--deep); color:#fff; border:none; padding:.9rem 2.5rem; border-radius:30px;
    font-size:.95rem; font-weight:600; cursor:pointer; font-family:inherit; }
  .modal-close:hover { background:var(--gold); color:var(--deep); }

  footer { background:var(--deep); color:#5A4A35; text-align:center; padding:1.5rem; font-size:.85rem; }
  footer span { color:var(--gold); }

  .c-paris{background:linear-gradient(135deg,#2C3E8C,#6A5ACD)} .c-maldives{background:linear-gradient(135deg,#00B4D8,#48CAE4)}
  .c-dubai{background:linear-gradient(135deg,#D4A017,#F4C542)} .c-kerala{background:linear-gradient(135deg,#43e97b,#38f9d7)}
  .c-goa{background:linear-gradient(135deg,#667eea,#764ba2)} .c-hyd{background:linear-gradient(135deg,#f7971e,#ffd200)}
  .c-mumbai{background:linear-gradient(135deg,#fc5c7d,#6a3093)} .c-pune{background:linear-gradient(135deg,#11998e,#38ef7d)}
  .c-delhi{background:linear-gradient(135deg,#ee0979,#ff6a00)} .c-tirupati{background:linear-gradient(135deg,#f9a825,#fdd835)}
  .c-ladakh{background:linear-gradient(135deg,#5C6BC0,#B39DDB)} .c-manali{background:linear-gradient(135deg,#4facfe,#00f2fe)}
  .c-rajasthan{background:linear-gradient(135deg,#fa709a,#fee140)} .c-bangkok{background:linear-gradient(135deg,#a18cd1,#fbc2eb)}

  @media (max-width:600px) {
    nav { padding:1rem 1.5rem; } nav ul { gap:1rem; }
    .packages,.day-trips,.booking-section { padding:3rem 1rem; }
    .form-row { grid-template-columns:1fr; } .form-container { padding:1.5rem; }
  }
</style>
</head>
<body>

<nav>
  <div class="logo">Infinity<span> Travels</span></div>
  <ul>
    <li><a href="#packages">Packages</a></li>
    <li><a href="#daytrips">Day Trips</a></li>
    <li><a href="#booking">Book Now</a></li>
  </ul>
</nav>

<section class="hero">
  <div class="hero-badge">✈️ India &amp; International Packages</div>
  <h1>Travel Beyond<br><span>Your Limits</span></h1>
  <p>Handpicked travel packages for every kind of explorer. From local day trips to international adventures — we've got you covered.</p>
  <a href="#packages" class="hero-btn">Explore Packages →</a>
</section>

{% macro card(p) %}
<div class="card" data-name="{{ p.name }}">
  <div class="card-img {{ p.css }}">
    <img src="{{ p.img }}" alt="{{ p.name }}" loading="lazy" onerror="this.remove()">
    {% if p.dur %}<span class="badge-days">{{ p.dur }}</span>{% endif %}
  </div>
  <div class="card-body">
    <h3>{{ p.name }}</h3>
    <div class="location">📍 {{ p.loc }}</div>
    <div class="card-features">
      {% for t in p.tags %}<span class="feature-tag">{{ t }}</span>{% endfor %}
    </div>
    <div class="card-footer">
      <div class="price">₹{{ p.price | inr }} <span>/person</span></div>
      <button class="select-btn" type="button">Select</button>
    </div>
  </div>
</div>
{% endmacro %}

<section class="packages" id="packages">
  <div class="section-title">
    <div class="section-tag">✈️ Holiday Packages</div>
    <h2>Our Travel Packages</h2>
    <p>Click on any package to select and book</p>
  </div>
  <div class="cards">{% for p in packages %}{{ card(p) }}{% endfor %}</div>
</section>

<section class="day-trips" id="daytrips">
  <div class="section-title">
    <div class="section-tag">🌅 Quick Escapes</div>
    <h2>Day Escapades</h2>
    <p>Short on time? These 1-day trips are perfect for a quick getaway!</p>
  </div>
  <div class="cards day">{% for p in day_trips %}{{ card(p) }}{% endfor %}</div>
</section>

<section class="booking-section" id="booking">
  <div class="section-title">
    <h2>Book Your Trip</h2>
    <p>Fill in your details and confirm your booking</p>
  </div>
  <div class="form-container">
    <div class="selected-package-display" id="pkgDisplay">
      <h4>Selected Package</h4>
      <p id="pkgName"></p>
    </div>

    <div class="form-row">
      <div class="form-group"><label>Full Name</label><input type="text" id="fullName" placeholder="Your name"></div>
      <div class="form-group"><label>Email</label><input type="email" id="email" placeholder="you@email.com"></div>
    </div>
    <div class="form-row">
      <div class="form-group"><label>Phone Number</label><input type="tel" id="phone" placeholder="9876543210"></div>
      <div class="form-group"><label>Travel Date</label><input type="date" id="travelDate" min="{{ today }}"></div>
    </div>
    <div class="form-row">
      <div class="form-group">
        <label>No. of Persons</label>
        <select id="persons">
          {% for i in range(1, 11) %}<option value="{{ i }}">{{ i }} Person{{ 's' if i > 1 }}</option>{% endfor %}
        </select>
      </div>
      <div class="form-group">
        <label>Package</label>
        <select id="pkgSelect">
          <option value="">-- Select Package --</option>
          <optgroup label="✈️ Holiday Packages">
            {% for p in packages %}<option value="{{ p.name }}">{{ p.name }} — ₹{{ p.price | inr }}</option>{% endfor %}
          </optgroup>
          <optgroup label="🌅 Day Escapades">
            {% for p in day_trips %}<option value="{{ p.name }}">{{ p.name }} — ₹{{ p.price | inr }}</option>{% endfor %}
          </optgroup>
        </select>
      </div>
    </div>

    <div class="total-price"><span>Total Amount</span><strong id="totalAmt">₹0</strong></div>
    <div class="error" id="formError"></div>
    <button class="book-btn" id="bookBtn" type="button">🎒 Confirm Booking</button>
  </div>
</section>

<footer>
  <p>© {{ year }} <span>Infinity Travels</span>. All rights reserved. | Made with ❤️ for Explorers</p>
</footer>

<div class="modal-overlay" id="modal">
  <div class="modal">
    <div class="modal-icon">🎉</div>
    <h2>Booking Confirmed!</h2>
    <p class="lead">Your dream trip is booked! Our team will contact you shortly.</p>
    <p class="lead" id="emailNote" style="margin-top:-1rem"></p>
    <div class="booking-id"><span>Booking ID</span><strong id="bookingId"></strong></div>
    <div class="modal-details" id="modalDetails"></div>
    <button class="modal-close" id="closeBtn" type="button">Done ✓</button>
  </div>
</div>

<script>
  const PRICES = {{ prices | tojson }};
  const $ = id => document.getElementById(id);
  const money = n => '₹' + Number(n).toLocaleString('en-IN');
  let selected = '';

  function setSelected(name) {
    selected = name;
    document.querySelectorAll('.card').forEach(c => c.classList.toggle('selected', c.dataset.name === name));
    $('pkgSelect').value = name;
    if (name) {
      $('pkgDisplay').classList.add('show');
      $('pkgName').textContent = name + ' — ' + money(PRICES[name]) + '/person';
    } else {
      $('pkgDisplay').classList.remove('show');
    }
    calcTotal();
  }

  function calcTotal() {
    const total = selected ? PRICES[selected] * parseInt($('persons').value, 10) : 0;
    $('totalAmt').textContent = money(total);
  }

  document.querySelectorAll('.card').forEach(card => card.addEventListener('click', () => {
    setSelected(card.dataset.name);
    setTimeout(() => $('booking').scrollIntoView({ behavior: 'smooth' }), 300);
  }));
  $('pkgSelect').addEventListener('change', e => setSelected(e.target.value));
  $('persons').addEventListener('change', calcTotal);

  $('bookBtn').addEventListener('click', async () => {
    $('formError').textContent = '';
    $('bookBtn').disabled = true;
    try {
      const res = await fetch('/book', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: $('fullName').value, email: $('email').value, phone: $('phone').value,
          date: $('travelDate').value, persons: $('persons').value, package: selected
        })
      });
      const data = await res.json();
      if (!res.ok) { $('formError').textContent = '⚠️ ' + data.error; return; }
      showModal(data);
    } catch (err) {
      $('formError').textContent = '⚠️ Could not reach the server. Please try again.';
    } finally {
      $('bookBtn').disabled = false;
    }
  });

  function showModal(b) {
    $('bookingId').textContent = b.id;
    $('emailNote').textContent = b.emailed ? '📧 A confirmation email is on its way to ' + b.email + '.' : '';
    const box = $('modalDetails');
    box.textContent = '';
    [['👤 Name', b.name], ['📧 Email', b.email], ['📦 Package', b.package],
     ['📅 Travel Date', b.date], ['👥 Persons', b.persons], ['💰 Total Amount', money(b.total)]
    ].forEach(([label, value]) => {
      const p = document.createElement('p');
      const s = document.createElement('strong');
      s.textContent = label + ': ';
      p.append(s, document.createTextNode(value));   // textContent only -> no HTML injection
      box.appendChild(p);
    });
    $('modal').classList.add('show');
  }

  $('closeBtn').addEventListener('click', () => {
    $('modal').classList.remove('show');
    ['fullName', 'email', 'phone', 'travelDate'].forEach(id => $(id).value = '');
    $('persons').value = '1';
    setSelected('');
    window.scrollTo({ top: 0, behavior: 'smooth' });
  });
</script>
</body>
</html>
"""

# ---------------------------------------------------------------- EMAIL
def _customer_email(b: dict) -> EmailMessage:
    rows = [("Booking ID", b["id"]), ("Package", b["package"]), ("Travel date", b["date"]),
            ("Persons", str(b["persons"])), ("Total amount", "₹" + inr(b["total"]))]
    text = (f"Hi {b['name']},\n\nYour booking with Infinity Travels is confirmed.\n\n"
            + "\n".join(f"{k}: {v}" for k, v in rows)
            + "\n\nOur team will contact you shortly on " + b["phone"]
            + " with the next steps.\n\nThank you for choosing Infinity Travels!\n")
    table = "".join(
        f"<tr><td style='padding:6px 14px 6px 0;color:#6B5B45'>{escape(k)}</td>"
        f"<td style='padding:6px 0'><b>{escape(v)}</b></td></tr>" for k, v in rows)
    html = (
        "<div style='font-family:Arial,sans-serif;max-width:520px;margin:auto;color:#1A1208'>"
        "<h2 style='color:#C8922A'>Booking confirmed 🎉</h2>"
        f"<p>Hi {escape(b['name'])},</p><p>Your booking with <b>Infinity Travels</b> is confirmed.</p>"
        f"<table>{table}</table>"
        f"<p>Our team will contact you shortly on {escape(b['phone'])} with the next steps.</p>"
        "<p>Thank you for choosing Infinity Travels!</p></div>")
    msg = EmailMessage()
    msg["Subject"] = f"Booking confirmed - {b['id']} | Infinity Travels"
    msg["From"] = MAIL_FROM
    msg["To"] = b["email"]
    msg.set_content(text)
    msg.add_alternative(html, subtype="html")
    return msg


def _owner_email(b: dict) -> EmailMessage:
    msg = EmailMessage()
    msg["Subject"] = f"New booking {b['id']} - {b['package']}"
    msg["From"] = MAIL_FROM
    msg["To"] = OWNER_EMAIL
    msg["Reply-To"] = b["email"]
    msg.set_content(
        f"New booking received\n\nID: {b['id']}\nName: {b['name']}\nEmail: {b['email']}\n"
        f"Phone: {b['phone']}\nPackage: {b['package']}\nTravel date: {b['date']}\n"
        f"Persons: {b['persons']}\nTotal: ₹{inr(b['total'])}\n")
    return msg


def _smtp_send(messages):
    ctx = ssl.create_default_context()
    if SMTP_PORT == 465:
        server = smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, context=ctx, timeout=20)
    else:
        server = smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=20)
        server.starttls(context=ctx)
    with server:
        server.login(SMTP_USER, SMTP_PASSWORD)
        for m in messages:
            server.send_message(m)


def send_booking_emails(b: dict) -> None:
    """Runs in a background thread so the customer isn't kept waiting."""
    try:
        msgs = [_customer_email(b)]
        if OWNER_EMAIL:
            msgs.append(_owner_email(b))
        _smtp_send(msgs)
        log.info("Emails sent for %s", b["id"])
    except Exception:
        log.exception("Could not send emails for %s", b["id"])


# --------------------------------------------------------------- ROUTES
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
PHONE_RE = re.compile(r"^[6-9]\d{9}$")


@app.route("/")
def index():
    return render_template_string(
        PAGE,
        packages=PACKAGES,
        day_trips=DAY_TRIPS,
        prices=PRICE_BY_NAME,
        today=date.today().isoformat(),   # local date, not UTC
        year=date.today().year,
    )


@app.post("/book")
def book():
    data = request.get_json(silent=True) or {}
    name = str(data.get("name", "")).strip()
    email = str(data.get("email", "")).strip()
    phone = re.sub(r"[\s-]", "", str(data.get("phone", ""))).removeprefix("+91")
    pkg = str(data.get("package", "")).strip()

    def fail(msg):
        return jsonify(error=msg), 400

    if not name:
        return fail("Please enter your full name.")
    if not EMAIL_RE.match(email):
        return fail("Please enter a valid email.")
    if not PHONE_RE.match(phone):
        return fail("Please enter a valid 10-digit Indian mobile number.")
    try:
        travel = datetime.strptime(str(data.get("date", "")), "%Y-%m-%d").date()
    except ValueError:
        return fail("Please select a travel date.")
    if travel < date.today():
        return fail("Travel date can't be in the past.")
    if pkg not in PRICE_BY_NAME:
        return fail("Please select a travel package.")
    try:
        persons = int(data.get("persons", 1))
    except (TypeError, ValueError):
        persons = 0
    if not 1 <= persons <= 10:
        return fail("Persons must be between 1 and 10.")

    total = PRICE_BY_NAME[pkg] * persons          # price comes from the server
    created = datetime.now().isoformat(timespec="seconds")

    con = get_db()
    try:
        for _ in range(10):                       # retry on the rare ID clash
            booking_id = f"IT-{random.randint(100000, 999999)}"
            try:
                with con:
                    con.execute(
                        "INSERT INTO bookings VALUES (?,?,?,?,?,?,?,?,?)",
                        (booking_id, created, name, email, phone, pkg,
                         travel.isoformat(), persons, total),
                    )
                break
            except sqlite3.IntegrityError:
                continue
        else:
            return jsonify(error="Could not create booking, please try again."), 500
    finally:
        con.close()

    result = dict(id=booking_id, name=name, email=email, phone=phone, package=pkg,
                  date=travel.strftime("%d %B %Y"), persons=persons, total=total)
    if EMAIL_ENABLED:
        threading.Thread(target=send_booking_emails, args=(result,), daemon=True).start()
    return jsonify(**result, emailed=EMAIL_ENABLED)


def _authorised():
    auth = request.authorization
    return bool(
        ADMIN_PASSWORD and auth
        and hmac.compare_digest(auth.password or "", ADMIN_PASSWORD)
    )


@app.get("/admin")
def admin():
    if not _authorised():
        return Response("Login required", 401,
                        {"WWW-Authenticate": 'Basic realm="Infinity Travels admin"'})
    con = get_db()
    rows = con.execute("SELECT * FROM bookings ORDER BY created_at DESC").fetchall()
    con.close()
    head = ["ID", "Created", "Name", "Email", "Phone", "Package", "Travel date", "Persons", "Total (₹)"]
    body = "".join(
        "<tr>" + "".join(f"<td>{escape(str(c))}</td>" for c in r) + "</tr>" for r in rows
    )
    return (
        "<!doctype html><meta charset=utf-8><title>Bookings</title>"
        "<style>body{font-family:sans-serif;margin:2rem}table{border-collapse:collapse;width:100%}"
        "td,th{border:1px solid #ccc;padding:.4rem .6rem;font-size:.9rem;text-align:left}"
        "th{background:#f3ead7}</style>"
        f"<h1>Bookings ({len(rows)})</h1><table><tr>"
        + "".join(f"<th>{h}</th>" for h in head) + "</tr>" + body + "</table>"
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)),
            debug=os.environ.get("FLASK_DEBUG") == "1")
