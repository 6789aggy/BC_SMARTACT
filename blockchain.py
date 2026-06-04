from flask import Flask, request, jsonify, render_template_string, redirect
import sqlite3
import re
from datetime import datetime, timedelta


app = Flask(__name__)

# ==========================================
# DATABASE
# ==========================================

DB_NAME = "hydroponic_pro.db"

# ==========================================
# SENSOR DATA
# ==========================================

sensor_data = {

    "ph": 0,

    "turbidity": 0,

    "level": 0,

    "flow": 0,

    "pump": "OFF"

}

# ==========================================
# SYSTEM STATUS
# ==========================================

status_text = "Khởi động"

message_text = "Đang chờ dữ liệu"

mode = "THỦ CÔNG"

recommended_seconds = 0

auto_end_time = None

pump_command = ""

# ==========================================
# SESSION STORAGE
# ==========================================

pump_session = None

pending_blockchain = None

# ==========================================
# CHART BUFFER
# ==========================================

chart_history = {

    "time": [],

    "ph": [],

    "turbidity": [],

    "level": [],

    "flow": []

}

MAX_POINTS = 30

# ==========================================
# DATABASE INIT
# ==========================================

def init_db():

    conn = sqlite3.connect(DB_NAME)

    c = conn.cursor()

    c.execute("""

    CREATE TABLE IF NOT EXISTS logs(

        id INTEGER PRIMARY KEY AUTOINCREMENT,

        date TEXT,

        start_time TEXT,

        end_time TEXT,

        duration INTEGER,

        ph REAL,

        turbidity REAL,

        level REAL,

        flow REAL

    )

    """)

    conn.commit()

    conn.close()

# ==========================================
# SAVE SESSION LOG
# ==========================================

def save_session_log(data):

    conn = sqlite3.connect(DB_NAME)

    c = conn.cursor()

    c.execute("""

    INSERT INTO logs(

        date,

        start_time,

        end_time,

        duration,

        ph,

        turbidity,

        level,

        flow

    )

    VALUES(

        ?,?,?,?,?,?,?,?

    )

    """,

    (

        data["date"],

        data["start_time"],

        data["end_time"],

        data["duration"],

        data["ph"],

        data["turbidity"],

        data["level"],

        data["flow"]

    ))

    conn.commit()

    conn.close()

# ==========================================
# GET LOGS
# ==========================================

def get_logs(limit=50):

    conn = sqlite3.connect(DB_NAME)

    c = conn.cursor()

    c.execute("""

    SELECT

        date,

        start_time,

        end_time,

        duration,

        ph,

        turbidity,

        level,

        flow

    FROM logs

    ORDER BY id DESC

    LIMIT ?

    """,

    (limit,))

    rows = c.fetchall()

    conn.close()

    return rows

# ==========================================
# NUMBER EXTRACTOR
# ==========================================

def extract_number(text):

    m = re.search(

        r"[-+]?\d*\.?\d+",

        str(text)

    )

    if m:

        return float(m.group())

    return 0

# ==========================================
# PARSE SENSOR STRING
# ==========================================

def parse_sensor(raw):

    global sensor_data

    parts = raw.split(",")

    parsed = {}

    for p in parts:

        if ":" in p:

            k, v = p.split(":", 1)

            parsed[k.strip()] = v.strip()

    sensor_data["ph"] = extract_number(
        parsed.get("PH", 0)
    )

    sensor_data["turbidity"] = extract_number(
        parsed.get("TUR", 0)
    )

    sensor_data["level"] = extract_number(
        parsed.get("LEVEL", 0)
    )

    sensor_data["flow"] = extract_number(
        parsed.get("FLOW", 0)
    )

    sensor_data["pump"] = parsed.get(
        "PUMP",
        "OFF"
    )

# ==========================================
# CHART HISTORY
# ==========================================

def update_chart_data():

    now = datetime.now().strftime(
        "%H:%M:%S"
    )

    chart_history["time"].append(now)

    chart_history["ph"].append(
        sensor_data["ph"]
    )

    chart_history["turbidity"].append(
        sensor_data["turbidity"]
    )

    chart_history["level"].append(
        sensor_data["level"]
    )

    chart_history["flow"].append(
        sensor_data["flow"]
    )

    if len(chart_history["time"]) > MAX_POINTS:

        for key in chart_history:

            chart_history[key].pop(0)

# ==========================================
# AI ANALYSIS
# ==========================================

def analyze():

    global status_text
    global message_text
    global recommended_seconds

    turb = sensor_data["turbidity"]

    level = sensor_data["level"]

    flow = sensor_data["flow"]

    pump = sensor_data["pump"]

    recommended_seconds = 0

    if level < 100:

        status_text = "NGUY HIỂM"

        message_text = "Mực nước quá thấp"

        return

    if pump == "ON" and flow < 0.1:

        status_text = "CẢNH BÁO"

        message_text = (
            "Bơm chạy nhưng không có lưu lượng"
        )

        return

    if turb > 900:

        status_text = "NGUY HIỂM"

        message_text = "Nước rất đục"

        recommended_seconds = 30

    elif turb > 700:

        status_text = "CẢNH BÁO"

        message_text = "Nước đục cao"

        recommended_seconds = 20

    elif turb > 500:

        status_text = "CẢNH BÁO"

        message_text = "Nước hơi đục"

        recommended_seconds = 10

    else:

        status_text = "AN TOÀN"

        message_text = "Hệ thống ổn định"

# ==========================================
# SENSOR RECEIVE
# ==========================================

@app.route(
    "/sensor",
    methods=["POST"]
)
def sensor():

    raw = request.data.decode(
        errors="ignore"
    )

    parse_sensor(raw)

    analyze()

    update_chart_data()

    return "OK"

# ==========================================
# PUMP ON
# ==========================================

@app.route(
    "/pump/on",
    methods=["POST"]
)
def pump_on():

    global pump_command
    global pump_session

    pump_session = {

        "start_dt":
        datetime.now(),

        "date":
        datetime.now().strftime(
            "%d/%m/%Y"
        ),

        "start_time":
        datetime.now().strftime(
            "%H:%M:%S"
        ),

        "ph":
        sensor_data["ph"],

        "turbidity":
        sensor_data["turbidity"],

        "level":
        sensor_data["level"],

        "flow":
        sensor_data["flow"]

    }

    pump_command = "PUMP_ON"

    return redirect("/")

# ==========================================
# PUMP OFF
# ==========================================

@app.route(
    "/pump/off",
    methods=["POST"]
)
def pump_off():

    global pump_command
    global pump_session
    global pending_blockchain

    if pump_session:

        end_dt = datetime.now()

        duration = int(

            (
                end_dt
                -
                pump_session["start_dt"]

            ).total_seconds()

        )

        log_data = {

            "date":
            pump_session["date"],

            "start_time":
            pump_session["start_time"],

            "end_time":
            end_dt.strftime(
                "%H:%M:%S"
            ),

            "duration":
            duration,

            "ph":
            pump_session["ph"],

            "turbidity":
            pump_session["turbidity"],

            "level":
            pump_session["level"],

            "flow":
            pump_session["flow"]

        }

        save_session_log(
            log_data
        )

        pending_blockchain = log_data

        pump_session = None

    pump_command = "PUMP_OFF"

    return redirect("/")

# ==========================================
# AUTO MODE
# ==========================================

@app.route(
    "/run_auto",
    methods=["POST"]
)
def run_auto():

    global mode
    global pump_command
    global auto_end_time
    global pump_session

    analyze()

    if recommended_seconds <= 0:

        return redirect("/")

    mode = "TỰ ĐỘNG"

    auto_end_time = (

        datetime.now()

        +

        timedelta(
            seconds=
            recommended_seconds
        )

    )

    # tạo phiên tưới

    pump_session = {

        "start_dt":
        datetime.now(),

        "date":
        datetime.now().strftime(
            "%d/%m/%Y"
        ),

        "start_time":
        datetime.now().strftime(
            "%H:%M:%S"
        ),

        "ph":
        sensor_data["ph"],

        "turbidity":
        sensor_data["turbidity"],

        "level":
        sensor_data["level"],

        "flow":
        sensor_data["flow"]

    }

    pump_command = "PUMP_ON"

    return redirect("/")

# ==========================================
# AUTO ENGINE
# ==========================================

def auto_logic():

    global mode
    global auto_end_time
    global pump_command
    global pump_session
    global pending_blockchain

    if mode != "TỰ ĐỘNG":

        return

    if auto_end_time is None:

        return

    if datetime.now() < auto_end_time:

        return

    # tự động kết thúc phiên tưới

    if pump_session:

        end_dt = datetime.now()

        duration = int(

            (
                end_dt
                -
                pump_session["start_dt"]

            ).total_seconds()

        )

        log_data = {

            "date":
            pump_session["date"],

            "start_time":
            pump_session["start_time"],

            "end_time":
            end_dt.strftime(
                "%H:%M:%S"
            ),

            "duration":
            duration,

            "ph":
            pump_session["ph"],

            "turbidity":
            pump_session["turbidity"],

            "level":
            pump_session["level"],

            "flow":
            pump_session["flow"]

        }

        save_session_log(
            log_data
        )

        pending_blockchain = log_data

        pump_session = None

    pump_command = "PUMP_OFF"

    auto_end_time = None

    mode = "THỦ CÔNG"

# ==========================================
# COMMAND FOR ESP8266
# ==========================================

@app.route("/command")
def command():

    global pump_command

    auto_logic()

    cmd = pump_command

    pump_command = ""

    return cmd

# ==========================================
# BLOCKCHAIN DATA API
# ==========================================

@app.route(
    "/api/blockchain_data"
)
def blockchain_data():

    global pending_blockchain

    if pending_blockchain is None:

        return jsonify({

            "ready": False

        })

    return jsonify({

        "ready": True,

        "date":
        pending_blockchain["date"],

        "start_time":
        pending_blockchain["start_time"],

        "end_time":
        pending_blockchain["end_time"],

        "duration":
        pending_blockchain["duration"],

        "ph":
        pending_blockchain["ph"],

        "turbidity":
        pending_blockchain["turbidity"],

        "level":
        pending_blockchain["level"],

        "flow":
        pending_blockchain["flow"]

    })

# ==========================================
# CLEAR BLOCKCHAIN DATA
# ==========================================

@app.route(
    "/clear_blockchain_data",
    methods=["POST"]
)
def clear_blockchain_data():

    global pending_blockchain

    pending_blockchain = None

    return "OK"

# ==========================================
# STATUS API
# ==========================================

@app.route(
    "/api/status"
)
def api_status():

    auto_logic()

    remaining = 0

    if auto_end_time:

        remaining = int(

            (
                auto_end_time
                -
                datetime.now()

            ).total_seconds()

        )

        if remaining < 0:

            remaining = 0

    return jsonify({

        "ph":
        sensor_data["ph"],

        "turbidity":
        sensor_data["turbidity"],

        "level":
        sensor_data["level"],

        "flow":
        sensor_data["flow"],

        "pump":
        sensor_data["pump"],

        "mode":
        mode,

        "status":
        status_text,

        "message":
        message_text,

        "recommendation":

        (
            f"Đề xuất bơm "
            f"{recommended_seconds} giây"
        )

        if recommended_seconds > 0

        else

        "Không cần bơm",

        "timer":

        (
            f"Tự tắt sau "
            f"{remaining} giây"
        )

        if mode == "TỰ ĐỘNG"

        else

        ""

    })

# ==========================================
# CHART API
# ==========================================

@app.route(
    "/api/chart"
)
def chart_api():

    return jsonify(

        chart_history

    )
# ==========================================
# DASHBOARD HTML
# ==========================================
HTML = """
<!DOCTYPE html>
<html lang="vi">

<head>

<meta charset="UTF-8">

<meta name="viewport"
      content="width=device-width,initial-scale=1.0">

<title>
GIÁM SÁT THỦY CANH THÔNG MINH
</title>

<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>

<script src="https://cdn.jsdelivr.net/npm/web3@latest/dist/web3.min.js"></script>

<style>

*{
    margin:0;
    padding:0;
    box-sizing:border-box;
    font-family:'Segoe UI',sans-serif;
}

html{
    scroll-behavior:smooth;
}

body{

    background:
    linear-gradient(
        135deg,
        #0f172a,
        #1e293b,
        #0f172a
    );

    color:white;

    min-height:100vh;
}

/* ===================================
SIDEBAR
=================================== */

.sidebar{

    position:fixed;

    left:0;
    top:0;

    width:240px;
    height:100vh;

    background:
    rgba(15,23,42,.95);

    border-right:
    1px solid rgba(
        255,255,255,.08
    );

    padding:25px;

    z-index:100;
}

.logo{

    font-size:24px;

    font-weight:bold;

    color:#38bdf8;

    margin-bottom:30px;
}

.nav-link{

    display:block;

    text-decoration:none;

    color:#cbd5e1;

    padding:14px 18px;

    margin-bottom:10px;

    border-radius:12px;

    transition:.3s;
}

.nav-link:hover{

    background:
    rgba(56,189,248,.12);

    color:#38bdf8;
}

.nav-link.active{

    background:
    linear-gradient(
        90deg,
        #0284c7,
        #38bdf8
    );

    color:white;

    font-weight:600;

    box-shadow:
    0 0 15px
    rgba(
        56,189,248,.4
    );
}

/* ===================================
MAIN
=================================== */

.main{

    margin-left:260px;

    padding:25px;
}

.title{

    font-size:34px;

    font-weight:bold;

    margin-bottom:25px;
}

/* ===================================
STATUS BAR
=================================== */

.status-bar{

    display:flex;

    gap:15px;

    flex-wrap:wrap;

    margin-bottom:20px;
}

.status-box{

    background:
    rgba(255,255,255,.08);

    backdrop-filter:
    blur(10px);

    padding:12px 20px;

    border-radius:14px;
}

/* ===================================
CARDS
=================================== */

.cards{

    display:grid;

    grid-template-columns:
    repeat(
        auto-fit,
        minmax(220px,1fr)
    );

    gap:20px;
}

.card{

    background:
    rgba(255,255,255,.08);

    backdrop-filter:
    blur(12px);

    border:
    1px solid rgba(
        255,255,255,.08
    );

    border-radius:20px;

    padding:25px;

    text-align:center;

    transition:.3s;
}

.card:hover{

    transform:
    translateY(-5px);
}

.card-title{

    color:#cbd5e1;

    margin-bottom:12px;

    font-size:17px;
}

.card-value{

    font-size:34px;

    font-weight:bold;
}

/* ===================================
STATUS
=================================== */

.alert-box{

    margin-top:25px;

    background:
    rgba(255,255,255,.08);

    border-radius:20px;

    padding:25px;
}

#status{

    font-size:28px;

    font-weight:bold;
}

.safe{
    color:#22c55e;
}

.warning{
    color:#facc15;
}

.danger{
    color:#ef4444;
}

/* ===================================
BUTTON
=================================== */

.controls{

    margin-top:25px;

    display:flex;

    justify-content:center;

    gap:15px;

    flex-wrap:wrap;
}

.btn{

    border:none;

    padding:14px 24px;

    border-radius:12px;

    color:white;

    cursor:pointer;

    font-size:16px;

    font-weight:600;

    transition:.3s;
}

.btn:hover{

    transform:scale(1.05);
}

.btn-on{

    background:
    linear-gradient(
        45deg,
        #16a34a,
        #22c55e
    );
}

.btn-off{

    background:
    linear-gradient(
        45deg,
        #dc2626,
        #ef4444
    );
}

.btn-auto{

    background:
    linear-gradient(
        45deg,
        #2563eb,
        #3b82f6
    );
}

.btn-chain{

    background:
    linear-gradient(
        45deg,
        #7c3aed,
        #a855f7
    );

    box-shadow:
    0 0 20px
    rgba(
        168,85,247,.4
    );
}

/* ===================================
CHART
=================================== */

.chart-box{

    margin-top:30px;

    background:
    rgba(255,255,255,.08);

    padding:20px;

    border-radius:20px;
}

canvas{

    max-height:400px;
}

/* ===================================
LOG TABLE
=================================== */

.logs{

    margin-top:30px;

    background:
    rgba(255,255,255,.08);

    padding:20px;

    border-radius:20px;
}

table{

    width:100%;

    border-collapse:collapse;
}

th{

    background:#2563eb;

    padding:12px;
}

td{

    padding:10px;

    text-align:center;

    border-bottom:
    1px solid rgba(
        255,255,255,.05
    );
}

/* ===================================
RESPONSIVE
=================================== */

@media(max-width:900px){

    .sidebar{
        display:none;
    }

    .main{
        margin-left:0;
    }
}

</style>

</head>

<body>

<div class="sidebar">

<div class="logo">
🌱 Hydroponic Pro
</div>

<a href="#top"
   class="nav-link active">
🏠 Dashboard
</a>

<a href="#chart"
   class="nav-link">
📊 Biểu đồ
</a>

<a href="#control"
   class="nav-link">
⚙ Điều khiển
</a>

<a href="#logs"
   class="nav-link">
📝 Nhật ký
</a>

</div>

<div id="top" class="main">

<div class="title">
GIÁM SÁT THỦY CANH THÔNG MINH
</div>

<div class="status-bar">

<div id="wallet"
     class="status-box">

Ví: Chưa kết nối

</div>

<div class="status-box">
ESP8266 ● Online
</div>

<div class="status-box">
Arduino UNO ● Online
</div>

</div>

<div class="cards">

<div class="card">
<div class="card-title">💧 pH</div>
<div id="ph" class="card-value">0</div>
</div>

<div class="card">
<div class="card-title">🌫 Độ đục</div>
<div id="turbidity" class="card-value">0</div>
</div>

<div class="card">
<div class="card-title">📏 Mực nước</div>
<div id="level" class="card-value">0</div>
</div>

<div class="card">
<div class="card-title">🌊 Lưu lượng</div>
<div id="flow" class="card-value">0</div>
</div>

<div class="card">
<div class="card-title">⚙ Bơm</div>
<div id="pump" class="card-value">OFF</div>
</div>

<div class="card">
<div class="card-title">🛡 Chế độ</div>
<div id="mode" class="card-value">THỦ CÔNG</div>
</div>

<div class="card">
<div class="card-title">⛓ Blockchain</div>
<div id="txhash" class="card-value">READY</div>
</div>

</div>

<div class="alert-box">

<div id="status">
Khởi động
</div>

<br>

<div id="message">
Đang chờ dữ liệu
</div>

<br>

<div id="recommendation">
Không có đề xuất
</div>

<br>

<div id="timer">
</div>

</div>

<div id="control" class="controls">

<form action="/run_auto"
      method="post">

<button class="btn btn-auto">
🤖 Tự động
</button>

</form>

<form action="/pump/on"
      method="post">

<button class="btn btn-on">
▶ Bật bơm
</button>

</form>

<form action="/pump/off"
      method="post">

<button class="btn btn-off">
■ Tắt bơm
</button>

</form>

<button
onclick="saveToBlockchain()"
class="btn btn-chain">

⛓ Ghi Blockchain

</button>

</div>

<!-- ===================================
CHART
=================================== -->

<div id="chart" class="chart-box">

<h2 style="margin-bottom:20px;">
📊 Biểu đồ cảm biến thời gian thực
</h2>

<canvas id="sensorChart"></canvas>

</div>

<!-- ===================================
LOG TABLE
=================================== -->

<div id="logs" class="logs">

<h2 style="margin-bottom:20px;">
📝 Nhật ký phiên tưới
</h2>

<table>

<thead>

<tr>

<th>Ngày</th>

<th>Bắt đầu</th>

<th>Kết thúc</th>

<th>TG(s)</th>

<th>pH</th>

<th>Độ đục</th>

<th>Mực nước</th>

<th>Lưu lượng</th>

</tr>

</thead>

<tbody>

{% for row in logs %}

<tr>

<td>{{row[0]}}</td>

<td>{{row[1]}}</td>

<td>{{row[2]}}</td>

<td>{{row[3]}}</td>

<td>{{row[4]}}</td>

<td>{{row[5]}}</td>

<td>{{row[6]}}</td>

<td>{{row[7]}}</td>

</tr>

{% endfor %}

</tbody>

</table>

</div>

</div>

<script>

// ==========================================
// CONTRACT CONFIG
// ==========================================

const CONTRACT_ADDRESS =
"0x06F3AF0F4084cF0c5414878395620bAc46382d28";

const CONTRACT_ABI = [
	{
		"inputs": [
			{
				"internalType": "uint256",
				"name": "_ph",
				"type": "uint256"
			},
			{
				"internalType": "uint256",
				"name": "_turbidity",
				"type": "uint256"
			},
			{
				"internalType": "uint256",
				"name": "_level",
				"type": "uint256"
			},
			{
				"internalType": "uint256",
				"name": "_flow",
				"type": "uint256"
			},
			{
				"internalType": "string",
				"name": "_pump",
				"type": "string"
			}
		],
		"name": "addRecord",
		"outputs": [],
		"stateMutability": "nonpayable",
		"type": "function"
	},
	{
		"inputs": [],
		"name": "getCount",
		"outputs": [
			{
				"internalType": "uint256",
				"name": "",
				"type": "uint256"
			}
		],
		"stateMutability": "view",
		"type": "function"
	},
	{
		"inputs": [
			{
				"internalType": "uint256",
				"name": "",
				"type": "uint256"
			}
		],
		"name": "records",
		"outputs": [
			{
				"internalType": "uint256",
				"name": "ph",
				"type": "uint256"
			},
			{
				"internalType": "uint256",
				"name": "turbidity",
				"type": "uint256"
			},
			{
				"internalType": "uint256",
				"name": "level",
				"type": "uint256"
			},
			{
				"internalType": "uint256",
				"name": "flow",
				"type": "uint256"
			},
			{
				"internalType": "string",
				"name": "pump",
				"type": "string"
			},
			{
				"internalType": "uint256",
				"name": "timestamp",
				"type": "uint256"
			}
		],
		"stateMutability": "view",
		"type": "function"
	}
]

// ==========================================
// CHART
// ==========================================

const ctx =
document
.getElementById(
    "sensorChart"
)
.getContext("2d");

const sensorChart =
new Chart(ctx,{

    type:"line",

    data:{

        labels:[],

        datasets:[

        {
            label:"pH",

            data:[],

            borderWidth:2
        },

        {
            label:"Độ đục",

            data:[],

            borderWidth:2
        },

        {
            label:"Mực nước",

            data:[],

            borderWidth:2
        },

        {
            label:"Lưu lượng",

            data:[],

            borderWidth:2
        }

        ]

    },

    options:{

        responsive:true,

        maintainAspectRatio:false

    }

});

// ==========================================
// STATUS REFRESH
// ==========================================

async function refreshStatus(){

    try{

        const response =
        await fetch(
            "/api/status"
        );

        const data =
        await response.json();

        document
        .getElementById("ph")
        .innerText =
        data.ph;

        document
        .getElementById("turbidity")
        .innerText =
        data.turbidity;

        document
        .getElementById("level")
        .innerText =
        data.level;

        document
        .getElementById("flow")
        .innerText =
        data.flow;

        document
        .getElementById("pump")
        .innerText =
        data.pump;

        document
        .getElementById("mode")
        .innerText =
        data.mode;

        document
        .getElementById("status")
        .innerText =
        data.status;

        document
        .getElementById("message")
        .innerText =
        data.message;

        document
        .getElementById(
            "recommendation"
        )
        .innerText =
        data.recommendation;

        document
        .getElementById(
            "timer"
        )
        .innerText =
        data.timer;

    }
    catch(e){

        console.log(e);

    }

}

// ==========================================
// CHART REFRESH
// ==========================================

async function refreshChart(){

    try{

        const response =
        await fetch(
            "/api/chart"
        );

        const data =
        await response.json();

        sensorChart.data.labels =
        data.time;

        sensorChart
        .data
        .datasets[0]
        .data =
        data.ph;

        sensorChart
        .data
        .datasets[1]
        .data =
        data.turbidity;

        sensorChart
        .data
        .datasets[2]
        .data =
        data.level;

        sensorChart
        .data
        .datasets[3]
        .data =
        data.flow;

        sensorChart.update();

    }
    catch(e){

        console.log(e);

    }

}

// ==========================================
// SIDEBAR ACTIVE
// ==========================================

document
.querySelectorAll(
'.nav-link'
)
.forEach(btn=>{

    btn.addEventListener(
    'click',

    function(){

        document
        .querySelectorAll(
        '.nav-link'
        )
        .forEach(

        x=>x.classList
        .remove(
            'active'
        )

        );

        this.classList
        .add(
            'active'
        );

    });

});

// ==========================================
// WALLET CONNECT
// ==========================================

async function connectWallet(){

    if(
        typeof window.ethereum
        === 'undefined'
    ){

        alert(
            "MetaMask chưa cài"
        );

        return;
    }

    try{

        const accounts =
        await ethereum.request({

            method:
            'eth_requestAccounts'

        });

        document
        .getElementById(
            "wallet"
        )
        .innerText =

        "Ví: "

        +

        accounts[0]
        .substring(0,6)

        +

        "..."

        +

        accounts[0]
        .slice(-4);

    }
    catch(err){

        console.log(err);

    }

}

// ==========================================
// SAVE BLOCKCHAIN
// ==========================================

async function saveToBlockchain(){

    if(
        typeof window.ethereum
        === 'undefined'
    ){

        alert(
            "MetaMask chưa cài"
        );

        return;
    }

    const response =
    await fetch(
        "/api/blockchain_data"
    );

    const sensor =
    await response.json();

    if(
        !sensor.ready
    ){

        alert(
            "Chưa có phiên tưới hoàn chỉnh"
        );

        return;
    }

    try{

        const web3 =
        new Web3(
            window.ethereum
        );

        const accounts =
        await ethereum.request({

            method:
            'eth_requestAccounts'

        });

        const contract =
        new web3.eth.Contract(

            CONTRACT_ABI,

            CONTRACT_ADDRESS

        );

        const tx =
        await contract.methods
        .addRecord(

            parseInt(
                sensor.ph
            ),

            parseInt(
                sensor.turbidity
            ),

            parseInt(
                sensor.level
            ),

            parseInt(
                sensor.flow
            ),

            String(
                sensor.duration
            ) + "s"

        )
        .send({

            from:
            accounts[0]

        });

        document
        .getElementById(
            "txhash"
        )
        .innerText =

        tx.transactionHash
        .substring(0,10)

        +

        "...";

        await fetch(

            "/clear_blockchain_data",

            {
                method:"POST"
            }

        );

        alert(
            "Ghi Blockchain thành công"
        );

    }
    catch(err){

        console.log(err);

        alert(
            err.message
        );

    }

}

// ==========================================
// ONLOAD
// ==========================================

window.onload =
async ()=>{

    await connectWallet();

    refreshStatus();

    refreshChart();

    setInterval(

        refreshStatus,

        2000

    );

    setInterval(

        refreshChart,

        3000

    );

};

</script>

</body>

</html>

"""

# ==========================================
# HOME PAGE
# ==========================================

@app.route("/")
def home():

    logs = get_logs(50)

    return render_template_string(

        HTML,

        logs=logs

    )

# ==========================================
# RAW SENSOR DATA
# ==========================================

@app.route("/api/raw")
def raw_data():

    return jsonify(

        sensor_data

    )

# ==========================================
# RESET DATABASE
# ==========================================

@app.route(
    "/reset_logs",
    methods=["POST"]
)
def reset_logs():

    conn = sqlite3.connect(
        DB_NAME
    )

    c = conn.cursor()

    c.execute(

        "DELETE FROM logs"

    )

    conn.commit()

    conn.close()

    return redirect("/")

# ==========================================
# SYSTEM INFO
# ==========================================

@app.route("/api/system")
def system_info():

    return jsonify({

        "project":

        "GIÁM SÁT THỦY CANH THÔNG MINH",

        "database":
        DB_NAME,

        "mode":
        mode,

        "status":
        status_text,

        "message":
        message_text,

        "pending_blockchain":

        pending_blockchain
        is not None

    })

# ==========================================
# APPLICATION START
# ==========================================

init_db()

# ==========================================
# MAIN
# ==========================================

if __name__ == "__main__":

    print(
        "=" * 50
    )

    print(
        "HYDROPONIC PRO STARTING..."
    )

    print(
        "DATABASE:",
        DB_NAME
    )

    print(
        "URL:"
    )

    print(
        "http://0.0.0.0:5000"
    )

    print(
        "=" * 50
    )

    app.run(

        host="0.0.0.0",

        port=5000,

        debug=True,

        threaded=True

    )