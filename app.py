from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session
import sqlite3
import os
from datetime import datetime, date, timedelta
from functools import wraps

app = Flask(__name__)
app.secret_key = 'sistema-coleta-zapia-2024'
DB_PATH = os.path.join(os.path.dirname(__file__), 'database', 'sistema.db')

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    conn = get_db()
    # Forçar a criação das colunas se não existirem (MIGRAÇÃO)
    try:
        conn.execute("ALTER TABLE agendamentos ADD COLUMN nome TEXT")
    except: pass
    try:
        conn.execute("ALTER TABLE agendamentos ADD COLUMN telefone TEXT")
    except: pass
    try:
        conn.execute("ALTER TABLE agendamentos ADD COLUMN endereco TEXT")
    except: pass
    try:
        conn.execute("ALTER TABLE agendamentos ADD COLUMN observacao TEXT")
    except: pass
    
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS clientes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL,
            telefone TEXT,
            endereco TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS agendamentos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cliente_id INTEGER NOT NULL,
            nome TEXT NOT NULL,
            telefone TEXT,
            endereco TEXT,
            data_coleta DATE NOT NULL,
            horario TIME NOT NULL,
            status TEXT DEFAULT 'pendente',
            observacao TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (cliente_id) REFERENCES clientes(id)
        );
        CREATE TABLE IF NOT EXISTS materiais (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL UNIQUE,
            preco_kg REAL NOT NULL
        );
        CREATE TABLE IF NOT EXISTS coletas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agendamento_id INTEGER NOT NULL,
            funcionario TEXT NOT NULL,
            data_coleta DATE NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (agendamento_id) REFERENCES agendamentos(id)
        );
        CREATE TABLE IF NOT EXISTS itens_coleta (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            coleta_id INTEGER NOT NULL,
            material_id INTEGER NOT NULL,
            quantidade_kg REAL NOT NULL,
            valor_total REAL NOT NULL,
            FOREIGN KEY (coleta_id) REFERENCES coletas(id),
            FOREIGN KEY (material_id) REFERENCES materiais(id)
        );
        CREATE TABLE IF NOT EXISTS dias_disponiveis (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            data DATE NOT NULL,
            horario_inicio TIME NOT NULL,
            horario_fim TIME NOT NULL,
            vagas INTEGER DEFAULT 1,
            UNIQUE(data, horario_inicio)
        );
    """)
    # Seed materiais
    # Materiais iniciais removidos para deixar o sistema limpo
    conn.commit()
    conn.close()

# ============================================================
# PAGINA INICIAL
# ============================================================
@app.route("/")
def index():
    return render_template("index.html")

# ============================================================
# AREA DO CLIENTE
# ============================================================
@app.route("/cliente")
def cliente_index():
    conn = get_db()
    agendamentos = conn.execute("""
        SELECT a.* FROM agendamentos a
        ORDER BY a.created_at DESC LIMIT 20
    """).fetchall()
    conn.close()
    return render_template("cliente/index.html", agendamentos=agendamentos)

@app.route("/cliente/agendar", methods=["GET", "POST"])
def cliente_agendar():
    conn = get_db()
    if request.method == "POST":
        nome = request.form["nome"]
        telefone = request.form["telefone"]
        endereco = request.form["endereco"]
        data_coleta = request.form["data_coleta"]
        horario = request.form["horario"]

        if not all([nome, data_coleta, horario]):
            flash("Preencha todos os campos obrigatorios!", "error")
            return redirect(url_for("cliente_agendar"))

        # Criar ou buscar cliente
        cliente = conn.execute("SELECT id FROM clientes WHERE nome=? AND telefone=?",
                               (nome, telefone)).fetchone()
        if cliente:
            cliente_id = cliente["id"]
            conn.execute("UPDATE clientes SET endereco=? WHERE id=?",
                         (endereco, cliente_id))
        else:
            conn.execute("INSERT INTO clientes (nome, telefone, endereco) VALUES (?, ?, ?)",
                         (nome, telefone, endereco))
            cliente_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

        # Inserir agendamento como PENDENTE
        conn.execute("""
            INSERT INTO agendamentos (cliente_id, nome, telefone, endereco, data_coleta, horario, status)
            VALUES (?, ?, ?, ?, ?, ?, 'pendente')
        """, (cliente_id, nome, telefone, endereco, data_coleta, horario))
        conn.commit()
        conn.close()
        flash("Solicitacao enviada! Aguarde a confirmacao da empresa.", "success")
        return redirect(url_for("cliente_index"))

    # GET - mostrar dias disponiveis
    hoje = date.today().isoformat()
    dias = conn.execute("""
        SELECT * FROM dias_disponiveis
        WHERE data >= ? ORDER BY data, horario_inicio
    """, (hoje,)).fetchall()
    conn.close()
    return render_template("cliente/agendar.html", dias=dias)

# ============================================================
# AREA DO FUNCIONARIO
# ============================================================
@app.route("/funcionario")
def funcionario_index():
    conn = get_db()
    hoje = date.today().isoformat()
    agendamentos = conn.execute("""
        SELECT a.* FROM agendamentos a
        WHERE a.status = 'agendado' AND a.data_coleta = ?
        ORDER BY a.horario
    """, (hoje,)).fetchall()
    conn.close()
    return render_template("funcionario/index.html", agendamentos=agendamentos)

@app.route("/funcionario/coleta/<int:id>", methods=["GET", "POST"])
def funcionario_coleta(id):
    conn = get_db()
    agendamento = conn.execute("SELECT * FROM agendamentos WHERE id=?", (id,)).fetchone()
    if not agendamento:
        conn.close()
        flash("Agendamento nao encontrado!", "error")
        return redirect(url_for("funcionario_index"))

    if request.method == "POST":
        funcionario = request.form["funcionario"]
        itens_raw = request.form.getlist("material_id[]")
        quantidades = request.form.getlist("quantidade[]")

        conn.execute(
            "INSERT INTO coletas (agendamento_id, funcionario, data_coleta) VALUES (?, ?, ?)",
            (id, funcionario, agendamento["data_coleta"])
        )
        coleta_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

        from collections import defaultdict
        material_totals = defaultdict(float)
        for mat_id, qtd_str in zip(itens_raw, quantidades):
            qtd = float(qtd_str) if qtd_str else 0
            if qtd > 0:
                material_totals[mat_id] += qtd

        for mat_id, qtd in material_totals.items():
            mat = conn.execute("SELECT * FROM materiais WHERE id=?", (mat_id,)).fetchone()
            valor = round(qtd * mat["preco_kg"], 2)
            conn.execute(
                "INSERT INTO itens_coleta (coleta_id, material_id, quantidade_kg, valor_total) VALUES (?, ?, ?, ?)",
                (coleta_id, mat_id, qtd, valor)
            )

        conn.execute("UPDATE agendamentos SET status='coletado' WHERE id=?", (id,))
        conn.commit()
        conn.close()
        flash(f"Coleta registrada por {funcionario}!", "success")
        return redirect(url_for("funcionario_index"))

    materiais = conn.execute("SELECT * FROM materiais ORDER BY nome").fetchall()
    conn.close()
    return render_template("funcionario/coleta.html", agendamento=agendamento, materiais=materiais)

@app.route("/funcionario/excluir/<int:id>", methods=["POST"])
def funcionario_excluir(id):
    conn = get_db()
    conn.execute("DELETE FROM itens_coleta WHERE coleta_id IN (SELECT id FROM coletas WHERE agendamento_id=?)", (id,))
    conn.execute("DELETE FROM coletas WHERE agendamento_id=?", (id,))
    conn.execute("DELETE FROM agendamentos WHERE id=?", (id,))
    conn.commit()
    conn.close()
    flash("Agendamento removido!", "info")
    return redirect(url_for("funcionario_index"))

# ============================================================
# AREA DO ADMIN
# ============================================================
@app.route("/admin")
def admin_index():
    conn = get_db()
    pendentes = conn.execute("SELECT COUNT(*) FROM agendamentos WHERE status='pendente'").fetchone()[0]
    agendados = conn.execute("SELECT COUNT(*) FROM agendamentos WHERE status='agendado'").fetchone()[0]
    coletados = conn.execute("SELECT COUNT(*) FROM agendamentos WHERE status='coletado'").fetchone()[0]
    conn.close()
    return render_template("admin/index.html", pendentes=pendentes, agendados=agendados, coletados=coletados)

@app.route("/admin/agendamentos")
def admin_agendamentos():
    conn = get_db()
    agendamentos = conn.execute("""
        SELECT a.* FROM agendamentos a
        ORDER BY a.created_at DESC
    """).fetchall()
    conn.close()
    return render_template("admin/agendamentos.html", agendamentos=agendamentos)

@app.route("/admin/excluir_agendamento/<int:id>", methods=["POST"])
def excluir_agendamento(id):
    conn = get_db()
    conn.execute("DELETE FROM itens_coleta WHERE coleta_id IN (SELECT id FROM coletas WHERE agendamento_id=?)", (id,))
    conn.execute("DELETE FROM coletas WHERE agendamento_id=?", (id,))
    conn.execute("DELETE FROM agendamentos WHERE id=?", (id,))
    conn.commit()
    conn.close()
    flash("Agendamento removido com sucesso!", "info")
    return redirect(url_for("admin_agendamentos"))

@app.route("/admin/aprovar/<int:id>", methods=["POST"])
def admin_aprovar(id):
    conn = get_db()
    conn.execute("UPDATE agendamentos SET status='agendado' WHERE id=?", (id,))
    conn.commit()
    conn.close()
    flash("Agendamento aprovado!", "success")
    return redirect(url_for("admin_agendamentos"))

@app.route("/admin/recusar/<int:id>", methods=["POST"])
def admin_recusar(id):
    observacao = request.form.get("observacao", "")
    conn = get_db()
    conn.execute("UPDATE agendamentos SET status='recusado', observacao=? WHERE id=?", (observacao, id))
    conn.commit()
    conn.close()
    flash("Agendamento recusado!", "info")
    return redirect(url_for("admin_agendamentos"))

@app.route("/admin/materiais", methods=["GET", "POST"])
def admin_materiais():
    conn = get_db()
    if request.method == "POST":
        nome = request.form["nome"]
        preco = float(request.form["preco_kg"])
        try:
            conn.execute("INSERT INTO materiais (nome, preco_kg) VALUES (?, ?)", (nome, preco))
            conn.commit()
            flash(f"Material {nome} adicionado!", "success")
        except sqlite3.IntegrityError:
            flash("Material ja existe!", "error")
        conn.close()
        return redirect(url_for("admin_materiais"))
    materiais = conn.execute("SELECT * FROM materiais ORDER BY nome").fetchall()
    conn.close()
    return render_template("admin/materiais.html", materiais=materiais)

@app.route("/admin/material/excluir/<int:id>", methods=["POST"])
def admin_excluir_material(id):
    conn = get_db()
    conn.execute("DELETE FROM materiais WHERE id=?", (id,))
    conn.commit()
    conn.close()
    flash("Material removido!", "info")
    return redirect(url_for("admin_materiais"))

# ============================================================
# DIAS DISPONIVEIS (Admin)
# ============================================================
@app.route("/admin/dias")
def admin_dias():
    conn = get_db()
    hoje = date.today().isoformat()
    dias = conn.execute("""
        SELECT id, data, horario_inicio, horario_fim, vagas FROM dias_disponiveis
        WHERE data >= ? ORDER BY data, horario_inicio
    """, (hoje,)).fetchall()
    conn.close()
    return render_template("admin/dias.html", dias=dias)

@app.route("/admin/dias/adicionar", methods=["POST"])
def admin_adicionar_dia():
    data = request.form["data"]
    horario_inicio = request.form["horario_inicio"]
    horario_fim = request.form["horario_fim"]
    vagas = int(request.form.get("vagas", 1))
    conn = get_db()
    try:
        conn.execute("""
            INSERT INTO dias_disponiveis (data, horario_inicio, horario_fim, vagas)
            VALUES (?, ?, ?, ?)
        """, (data, horario_inicio, horario_fim, vagas))
        conn.commit()
        flash(f"Dia {data} adicionado!", "success")
    except sqlite3.IntegrityError:
        flash("Este horario ja existe para esta data!", "error")
    conn.close()
    return redirect(url_for("admin_dias"))

@app.route("/admin/dias/excluir/<int:id>", methods=["POST"])
def admin_excluir_dia(id):
    conn = get_db()
    conn.execute("DELETE FROM dias_disponiveis WHERE id=?", (id,))
    conn.commit()
    conn.close()
    flash("Disponibilidade removida!", "info")
    return redirect(url_for("admin_dias"))

# ============================================================
# RELATORIO / IMPRIMIR
# ============================================================
@app.route("/admin/relatorio")
def admin_relatorio():
    conn = get_db()
    data_inicio = request.args.get("data_inicio", "")
    data_fim = request.args.get("data_fim", "")

    query = "SELECT a.* FROM agendamentos a WHERE 1=1"
    params = []
    if data_inicio:
        query += " AND a.data_coleta >= ?"
        params.append(data_inicio)
    if data_fim:
        query += " AND a.data_coleta <= ?"
        params.append(data_fim)
    query += " ORDER BY a.data_coleta, a.horario"

    agendamentos = conn.execute(query, params).fetchall()

    # Calcular totais
    total_coletas = sum(1 for a in agendamentos if a["status"] == "coletado")
    total_pendentes = sum(1 for a in agendamentos if a["status"] == "pendente")
    conn.close()
    return render_template("admin/relatorio.html",
                         agendamentos=agendamentos,
                         total_coletas=total_coletas,
                         total_pendentes=total_pendentes,
                         data_inicio=data_inicio,
                         data_fim=data_fim)

# ============================================================
# API
# ============================================================
@app.route("/api/materiais")
def api_materiais():
    conn = get_db()
    materiais = conn.execute("SELECT * FROM materiais ORDER BY nome").fetchall()
    conn.close()
    return jsonify([dict(m) for m in materiais])

@app.route("/api/calcular", methods=["POST"])
def api_calcular():
    data = request.json
    conn = get_db()
    total = 0
    detalhes = []
    for item in data["itens"]:
        mat = conn.execute("SELECT * FROM materiais WHERE id=?", (item["material_id"],)).fetchone()
        if mat and item["quantidade"] > 0:
            valor = round(item["quantidade"] * mat["preco_kg"], 2)
            total += valor
            detalhes.append({
                "material": mat["nome"],
                "preco_kg": mat["preco_kg"],
                "quantidade": item["quantidade"],
                "valor": valor
            })
    conn.close()
    return jsonify({"total": round(total, 2), "detalhes": detalhes})

@app.route("/api/dias-disponiveis")
def api_dias_disponiveis():
    conn = get_db()
    hoje = date.today().isoformat()
    dias = conn.execute("""
        SELECT data, horario_inicio, horario_fim FROM dias_disponiveis
        WHERE data >= ? ORDER BY data, horario_inicio
    """, (hoje,)).fetchall()
    conn.close()
    return jsonify([dict(d) for d in dias])


@app.route('/admin/material/editar/<int:id>', methods=['POST'])
def admin_editar_material(id):
    p = float(request.form['preco_kg'])
    conn = get_db()
    conn.execute('UPDATE materiais SET preco_kg=? WHERE id=?', (p, id))
    conn.commit()
    conn.close()
    flash('Preco atualizado!', 'success')
    return redirect(url_for('admin_materiais'))


@app.route("/admin/coletas")
def admin_coletas():
    conn = get_db()
    dados = conn.execute("""
        SELECT c.id, c.funcionario, c.data_coleta, a.nome as cliente
        FROM coletas c JOIN agendamentos a ON c.agendamento_id = a.id
        ORDER BY c.created_at DESC
    """).fetchall()
    conn.close()
    return render_template("admin/coletas.html", coletas=dados)

@app.route("/admin/coleta_detalhes/<int:id>")
def admin_coleta_detalhes(id):
    conn = get_db()
    coleta = conn.execute("""
        SELECT c.*, a.nome as cliente, a.endereco, a.telefone, a.data_coleta as data_agendada, a.horario
        FROM coletas c JOIN agendamentos a ON c.agendamento_id = a.id WHERE c.id=?
    """, (id,)).fetchone()
    if not coleta:
        conn.close()
        flash("Coleta nao encontrada!", "error")
        return redirect(url_for("admin_coletas"))
    itens = conn.execute("""
        SELECT i.*, m.nome as material_nome
        FROM itens_coleta i JOIN materiais m ON i.material_id = m.id WHERE i.coleta_id=?
    """, (id,)).fetchall()
    total = conn.execute("""
        SELECT COALESCE(SUM(valor_total), 0) FROM itens_coleta WHERE coleta_id=?
    """, (id,)).fetchone()[0]
    conn.close()
    return render_template("admin/coleta_detalhes.html", coleta=coleta, itens=itens, total=total)


if __name__ == "__main__":
    init_db()
    app.run(debug=True, host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
