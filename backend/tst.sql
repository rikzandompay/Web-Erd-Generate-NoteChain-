-- 1. Tabel Pelanggan
CREATE TABLE customers (
    customer_id INT PRIMARY KEY AUTO_INCREMENT,
    name VARCHAR(100) NOT NULL,
    phone VARCHAR(20),
    address TEXT
);

-- 2. Tabel Layanan
CREATE TABLE services (
    service_id INT PRIMARY KEY AUTO_INCREMENT,
    service_name VARCHAR(100) NOT NULL,
    unit VARCHAR(20), -- kg, pcs, m2
    price_per_unit DECIMAL(10, 2) NOT NULL
);

-- 3. Tabel Pesanan (Header)
CREATE TABLE orders (
    order_id INT PRIMARY KEY AUTO_INCREMENT,
    customer_id INT,
    order_date DATETIME DEFAULT CURRENT_TIMESTAMP,
    pickup_date DATETIME,
    status_order ENUM('Proses', 'Selesai', 'Diambil') DEFAULT 'Proses',
    status_payment ENUM('Belum Lunas', 'Lunas') DEFAULT 'Belum Lunas',
    total_amount DECIMAL(10, 2) DEFAULT 0.00,
    FOREIGN KEY (customer_id) REFERENCES customers(customer_id)
);

-- 4. Tabel Detail Pesanan (Rincian per item/layanan)
CREATE TABLE order_items (
    item_id INT PRIMARY KEY AUTO_INCREMENT,
    order_id INT,
    service_id INT,
    quantity DECIMAL(10, 2) NOT NULL,
    subtotal DECIMAL(10, 2) NOT NULL,
    FOREIGN KEY (order_id) REFERENCES orders(order_id) ON DELETE CASCADE,
    FOREIGN KEY (service_id) REFERENCES services(service_id)
);