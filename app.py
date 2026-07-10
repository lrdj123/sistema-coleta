from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session
import sqlite3
import os
from datetime import datetime

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
    conn.executescript('''
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
            data_coleta DATE NOT NULL,
            horario TIME NOT NULL,
            status TEXT DEFAULT 'agendado',
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
    ''')
    # Seed materiais padrao (sempre mantem)
    if conn.execute("SELECT COUNT(*) FROM materiais").fetchone()[0] == 0:
        materiais = [
            ('Papelão', 0.50),
            ('Ferro Velho', 1.20),
            ('Alumínio', 4.50),
            ('Plástico', 0.30),
            ('Vidro', 0.15),
            ('Cobre', 7.00),
            ('Aço', 0.80),
            ('Papel Branco', 0.40),
            ('Madeira', 0.10),
            ('Eletrônicos', 2.50),
        ]
        conn.executemany("INSERT INTO materiais (nome, preco_kg) VALUES (?, ?)", materiais)
        conn.commit()
    # Limpar dados de exemplo antigos (João Silva, etc)
    conn.execute("DELETE FROM itens_coleta")
    conn.execute("DELETE FROM coletas")
    conn.execute("DELETE FROM agendamentos")
    conn.execute("DELETE FROM clientes")
    conn.commit()
    conn.close()

init_db()

# ============================================================
# PÁGINA INICIAL
# ============================================================
@app.route('/')
def index():
    return render_template('index.html')

# ============================================================
# ÁREA DO CLIENTE
# ============================================================
@app.route('/cliente')
def cliente_home():
    conn = get_db()
    agendamentos = conn.execute("""
        SELECT a.*, c.nome 
        FROM agendamentos a
        JOIN clientes c ON a.cliente_id = c.id
        ORDER BY a.data_coleta DESC, a.horario DESC
    """).fetchall()
    conn.close()
    return render_template('cliente/index.html', agendamentos=agendamentos)

@app.route('/cliente/agendar', methods=['GET', 'POST'])
def cliente_agendar():
    if request.method == 'POST':
        nome = request.form['nome']
        telefone = request.form['telefone']
        endereco = request.form['endereco']
        data_coleta = request.form['data_coleta']
        horario = request.form['horario']
        
        conn = get_db()
        # Cria ou busca cliente
        cliente = conn.execute("SELECT id FROM clientes WHERE nome = ? AND telefone = ?", 
                               (nome, telefone)).fetchone()
        if not cliente:
            conn.execute("INSERT INTO clientes (nome, telefone, endereco) VALUES (?, ?, ?)",
                         (nome, telefone, endereco))
            conn.commit()
            cliente_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        else:
            cliente_id = cliente['id']
            conn.execute("UPDATE clientes SET endereco = ? WHERE id = ?", (endereco, cliente_id))
            conn.commit()
        
        conn.execute("INSERT INTO agendamentos (cliente_id, data_coleta, horario) VALUES (?, ?, ?)",
                     (cliente_id, data_coleta, horario))
        conn.commit()
        conn.close()
        
        flash('✅ Agendamento realizado com sucesso!', 'success')
        return redirect(url_for('cliente_home'))
    
    return render_template('cliente/agendar.html')

@app.route('/cliente/visualizar/<int:agendamento_id>')
def cliente_visualizar(agendamento_id):
    conn = get_db()
    agendamento = conn.execute("""
        SELECT a.*, c.nome, c.endereco, c.telefone
        FROM agendamentos a
        JOIN clientes c ON a.cliente_id = c.id
        WHERE a.id = ?
    """, (agendamento_id,)).fetchone()
    
    coleta = conn.execute("""
        SELECT * FROM coletas WHERE agendamento_id = ?
    """, (agendamento_id,)).fetchone()
    
    itens = []
    total_geral = 0
    if coleta:
        itens = conn.execute("""
            SELECT ic.*, m.nome as material_nome, m.preco_kg
            FROM itens_coleta ic
            JOIN materiais m ON ic.material_id = m.id
            WHERE ic.coleta_id = ?
        """, (coleta['id'],)).fetchall()
        total_geral = sum(item['valor_total'] for item in itens)
    
    conn.close()
    return render_template('cliente/visualizar.html', 
                         agendamento=agendamento, coleta=coleta, itens=itens, total_geral=total_geral)

# ============================================================
# ÁREA DO FUNCIONÁRIO
# ============================================================
@app.route('/funcionario')
def funcionario_home():
    conn = get_db()
    agendamentos = conn.execute("""
        SELECT a.*, c.nome, c.endereco, c.telefone
        FROM agendamentos a
        JOIN clientes c ON a.cliente_id = c.id
        WHERE a.status = 'agendado'
        ORDER BY a.data_coleta ASC, a.horario ASC
    """).fetchall()
    conn.close()
    return render_template('funcionario/index.html', agendamentos=agendamentos)

@app.route('/funcionario/coleta/<int:agendamento_id>')
def funcionario_coleta(agendamento_id):
    conn = get_db()
    agendamento = conn.execute("""
        SELECT a.*, c.nome, c.endereco, c.telefone
        FROM agendamentos a
        JOIN clientes c ON a.cliente_id = c.id
        WHERE a.id = ?
    """, (agendamento_id,)).fetchone()
    
    materiais = conn.execute("SELECT * FROM materiais ORDER BY nome").fetchall()
    conn.close()
    return render_template('funcionario/coleta.html', agendamento=agendamento, materiais=materiais)

@app.route('/funcionario/finalizar', methods=['POST'])
def funcionario_finalizar():
    agendamento_id = request.form['agendamento_id']
    funcionario = request.form['funcionario']
    data_coleta = request.form['data_coleta']
    
    conn = get_db()
    
    # Cria a coleta
    conn.execute("""INSERT INTO coletas (agendamento_id, funcionario, data_coleta) VALUES (?, ?, ?)""",
                 (agendamento_id, funcionario, data_coleta))
    conn.commit()
    coleta_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    
    # Salva cada item
    materiais = conn.execute("SELECT * FROM materiais").fetchall()
    for mat in materiais:
        qtd = request.form.get(f'material_{mat["id"]}', '0')
        if qtd and float(qtd) > 0:
            qtd = float(qtd)
            valor = round(qtd * mat['preco_kg'], 2)
            conn.execute("""INSERT INTO itens_coleta (coleta_id, material_id, quantidade_kg, valor_total) 
                         VALUES (?, ?, ?, ?)""", (coleta_id, mat['id'], qtd, valor))
    
    # Atualiza status do agendamento
    conn.execute("UPDATE agendamentos SET status = 'coletado' WHERE id = ?", (agendamento_id,))
    conn.commit()
    conn.close()
    
    flash(f'✅ Coleta #{coleta_id} finalizada com sucesso!', 'success')
    return redirect(url_for('funcionario_home'))

# ============================================================
# ÁREA ADMIN
# ============================================================
@app.route('/admin')
def admin_home():
    conn = get_db()
    
    # Estatísticas
    total_clientes = conn.execute("SELECT COUNT(*) FROM clientes").fetchone()[0]
    total_agendamentos = conn.execute("SELECT COUNT(*) FROM agendamentos").fetchone()[0]
    total_coletas = conn.execute("SELECT COUNT(*) FROM coletas").fetchone()[0]
    
    # Total arrecadado
    total_arrecadado = conn.execute("SELECT COALESCE(SUM(valor_total), 0) FROM itens_coleta").fetchone()[0]
    
    # Materiais mais coletados
    materiais_resumo = conn.execute("""
        SELECT m.nome, SUM(ic.quantidade_kg) as total_kg, SUM(ic.valor_total) as total_valor
        FROM itens_coleta ic
        JOIN materiais m ON ic.material_id = m.id
        GROUP BY m.nome
        ORDER BY total_kg DESC
    """).fetchall()
    
    # Últimas coletas
    ultimas_coletas = conn.execute("""
        SELECT c.id, c.funcionario, c.data_coleta, c.created_at,
               a.id as agendamento_id, cl.nome as cliente_nome,
               SUM(ic.valor_total) as total_coleta
        FROM coletas c
        JOIN agendamentos a ON c.agendamento_id = a.id
        JOIN clientes cl ON a.cliente_id = cl.id
        JOIN itens_coleta ic ON ic.coleta_id = c.id
        GROUP BY c.id
        ORDER BY c.created_at DESC
        LIMIT 20
    """).fetchall()
    
    conn.close()
    
    return render_template('admin/index.html', 
                         total_clientes=total_clientes,
                         total_agendamentos=total_agendamentos,
                         total_coletas=total_coletas,
                         total_arrecadado=total_arrecadado,
                         materiais_resumo=materiais_resumo,
                         ultimas_coletas=ultimas_coletas)

@app.route('/admin/agendamentos')
def admin_agendamentos():
    conn = get_db()
    agendamentos = conn.execute("""
        SELECT a.*, c.nome, c.telefone, c.endereco
        FROM agendamentos a
        JOIN clientes c ON a.cliente_id = c.id
        ORDER BY a.data_coleta DESC, a.horario DESC
    """).fetchall()
    conn.close()
    return render_template('admin/agendamentos.html', agendamentos=agendamentos)

@app.route('/admin/materiais', methods=['GET', 'POST'])
def admin_materiais():
    conn = get_db()
    if request.method == 'POST':
        nome = request.form['nome']
        preco = float(request.form['preco'])
        try:
            conn.execute("INSERT INTO materiais (nome, preco_kg) VALUES (?, ?)", (nome, preco))
            conn.commit()
            flash(f'✅ Material "{nome}" cadastrado!', 'success')
        except sqlite3.IntegrityError:
            flash(f'❌ Material "{nome}" já existe!', 'error')
    
    materiais = conn.execute("SELECT * FROM materiais ORDER BY nome").fetchall()
    conn.close()
    return render_template('admin/materiais.html', materiais=materiais)

@app.route('/admin/material/editar/<int:id>', methods=['POST'])
def admin_material_editar(id):
    conn = get_db()
    nome = request.form['nome']
    preco = float(request.form['preco'])
    conn.execute("UPDATE materiais SET nome = ?, preco_kg = ? WHERE id = ?", (nome, preco, id))
    conn.commit()
    conn.close()
    flash(f'✅ Material atualizado!', 'success')
    return redirect(url_for('admin_materiais'))

@app.route('/admin/material/deletar/<int:id>')
def admin_material_deletar(id):
    conn = get_db()
    conn.execute("DELETE FROM materiais WHERE id = ?", (id,))
    conn.commit()
    conn.close()
    flash(f'🗑️ Material removido!', 'info')
    return redirect(url_for('admin_materiais'))

# ============================================================
# API para cálculo (usada no front)
# ============================================================
@app.route('/api/materiais')
def api_materiais():
    conn = get_db()
    materiais = conn.execute("SELECT * FROM materiais ORDER BY nome").fetchall()
    conn.close()
    return jsonify([dict(m) for m in materiais])

@app.route('/api/calcular', methods=['POST'])
def api_calcular():
    data = request.json
    conn = get_db()
    total = 0
    detalhes = []
    for item in data['itens']:
        mat = conn.execute("SELECT * FROM materiais WHERE id = ?", (item['material_id'],)).fetchone()
        if mat and item['quantidade'] > 0:
            valor = round(item['quantidade'] * mat['preco_kg'], 2)
            total += valor
            detalhes.append({
                'material': mat['nome'],
                'preco_kg': mat['preco_kg'],
                'quantidade': item['quantidade'],
                'valor': valor
            })
    conn.close()
    return jsonify({'total': round(total, 2), 'detalhes': detalhes})


@app.route('/admin/excluir_agendamento/<int:id>', methods=['POST'])
def excluir_agendamento(id):
    conn = get_db()
    conn.execute("DELETE FROM agendamentos WHERE id = ?", (id,))
    conn.commit()
    conn.close()
    flash('🗑️ Agendamento removido com sucesso!', 'info')
    return redirect(url_for('admin_agendamentos'))

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)