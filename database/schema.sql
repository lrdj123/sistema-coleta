-- Banco de dados do Sistema de Coleta
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
    status TEXT DEFAULT 'agendado', -- agendado, coletado, cancelado
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