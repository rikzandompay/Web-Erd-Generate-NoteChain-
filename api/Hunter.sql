-- 1. Tabel Pengguna (Aplikasi Mobile)
CREATE TABLE users (
    user_id SERIAL PRIMARY KEY,
    device_id VARCHAR(50) UNIQUE NOT NULL, -- ID unik HP untuk anonimitas
    phone_number VARCHAR(20),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 2. Tabel Laporan (Pesan yang di-input user)
CREATE TABLE reports (
    report_id SERIAL PRIMARY KEY,
    user_id INT REFERENCES users(user_id) ON DELETE CASCADE,
    raw_text TEXT NOT NULL,                -- Pesan asli dialek lokal
    clean_text TEXT,                       -- Hasil preprocessing (Data Science)
    ai_score DECIMAL(5,2),                 -- Skor bahaya (0.00 - 100.00)
    label SMALLINT DEFAULT 0,              -- 0: Aman, 1: Bahaya
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 3. Tabel Entitas Ancaman (Hasil Ekstraksi NER)
-- Menyimpan link, nomor rekening, atau file APK yang ditemukan di pesan
CREATE TABLE threat_entities (
    entity_id SERIAL PRIMARY KEY,
    report_id INT REFERENCES reports(report_id) ON DELETE CASCADE,
    entity_type VARCHAR(50),               -- 'Link', 'APK', 'Bank_Account'
    entity_value TEXT NOT NULL,            -- Misal: 'http://resi-jnt.apk'
    is_malicious BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 4. Tabel Intelijen Peretas (Hacker Database)
-- Untuk mengelompokkan peretas berdasarkan IP atau Rekening
CREATE TABLE hacker_intelligence (
    hacker_id SERIAL PRIMARY KEY,
    ip_address VARCHAR(45),                -- IP Target Server Peretas
    bank_account VARCHAR(50),              -- No Rekening/E-wallet Penipu
    location_country VARCHAR(100),
    total_attacks_detected INT DEFAULT 1,
    last_active TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 5. Tabel Log Sandboxing (Analisis Teknis Malware)
-- Menyimpan detail hasil bedah file di environment Linux
CREATE TABLE sandboxing_logs (
    log_id SERIAL PRIMARY KEY,
    entity_id INT REFERENCES threat_entities(entity_id) ON DELETE CASCADE,
    malware_name VARCHAR(255),             -- Misal: 'SmsStealer.Android'
    ip_destination VARCHAR(45),            -- Server tujuan data curian
    screenshot_url TEXT,                   -- Path foto bukti dari server
    analysis_status VARCHAR(50),           -- 'Success', 'Failed'
    technical_logs TEXT,                   -- Log mentah dari terminal Linux
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);