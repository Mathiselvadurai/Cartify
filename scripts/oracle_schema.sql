-- Smart Product Recommendation and E-Commerce System
-- Oracle Database 26ai Schema Definition
-- Created for ECOMM_USER schema in FREEPDB1

-- Drop existing tables if needed (in reverse dependency order)
BEGIN
   FOR cur_rec IN (SELECT table_name FROM user_tables WHERE table_name IN ('REVIEWS', 'INTERACTIONS', 'ORDER_ITEMS', 'ORDERS', 'USERS', 'PRODUCTS')) LOOP
      EXECUTE IMMEDIATE 'DROP TABLE ' || cur_rec.table_name || ' CASCADE CONSTRAINTS';
   END LOOP;
END;
/

-- Drop existing sequences if needed
BEGIN
   FOR cur_rec IN (SELECT sequence_name FROM user_sequences WHERE sequence_name IN ('SEQ_ORDER_ID', 'SEQ_ORDER_ITEM_ID', 'SEQ_USER_ID', 'SEQ_INTERACTION_ID')) LOOP
      EXECUTE IMMEDIATE 'DROP SEQUENCE ' || cur_rec.sequence_name;
   END LOOP;
END;
/

-- 1. PRODUCTS TABLE
CREATE TABLE products (
    product_id          NUMBER(10) PRIMARY KEY,
    product_name        VARCHAR2(500),
    brand               VARCHAR2(255),
    variant             VARCHAR2(500),
    category            VARCHAR2(100),
    subcategory         VARCHAR2(100),
    product_type        VARCHAR2(150),
    gender              VARCHAR2(50),
    age_group           VARCHAR2(50),
    product_usage       VARCHAR2(100),
    season              VARCHAR2(50),
    color               VARCHAR2(100),
    product_description VARCHAR2(2000),
    search_keywords     VARCHAR2(2000),
    price_inr           NUMBER(10,2),
    sale_price_inr      NUMBER(10,2),
    discount_percent    NUMBER(5,1),
    rating              NUMBER(3,1),
    review_count        NUMBER(10),
    stock_quantity      NUMBER(10),
    sales_count         NUMBER(10),
    metrics_synthetic   NUMBER(1) DEFAULT 1,
    is_active           NUMBER(1) DEFAULT 1,
    image_url           VARCHAR2(2000),
    source_dataset      VARCHAR2(255)
);

-- 2. USERS TABLE
CREATE TABLE users (
    user_id             NUMBER(10) PRIMARY KEY,
    first_name          VARCHAR2(100),
    last_name           VARCHAR2(100),
    email               VARCHAR2(255) UNIQUE NOT NULL,
    password_hash       VARCHAR2(255) DEFAULT 'scrypt:32768:8:1$password123',
    gender              VARCHAR2(50),
    age                 NUMBER(3),
    city                VARCHAR2(100),
    state               VARCHAR2(100),
    signup_date         DATE,
    membership_tier     VARCHAR2(50),
    primary_device      VARCHAR2(50),
    acquisition_channel VARCHAR2(100),
    last_active_date    DATE,
    is_active           NUMBER(1) DEFAULT 1
);

-- 3. ORDERS TABLE
CREATE TABLE orders (
    order_id            NUMBER(10) PRIMARY KEY,
    user_id             NUMBER(10) NOT NULL REFERENCES users(user_id),
    order_date          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    order_status        VARCHAR2(50),
    payment_method      VARCHAR2(50),
    coupon_code         VARCHAR2(50),
    num_items           NUMBER(6),
    subtotal            NUMBER(10,2),
    discount_amount     NUMBER(10,2),
    shipping_fee        NUMBER(6,2),
    total_amount        NUMBER(10,2),
    shipping_city       VARCHAR2(100),
    shipping_state      VARCHAR2(100),
    delivery_date       DATE
);

-- 4. ORDER_ITEMS TABLE
CREATE TABLE order_items (
    order_item_id       NUMBER(10) PRIMARY KEY,
    order_id            NUMBER(10) NOT NULL REFERENCES orders(order_id),
    product_id          NUMBER(10) NOT NULL REFERENCES products(product_id),
    quantity            NUMBER(6),
    unit_price          NUMBER(10,2),
    line_total          NUMBER(10,2)
);

-- 5. INTERACTIONS TABLE
CREATE TABLE interactions (
    interaction_id      NUMBER(10) PRIMARY KEY,
    user_id             NUMBER(10) NOT NULL REFERENCES users(user_id),
    session_id          NUMBER(10),
    product_id          NUMBER(10) NOT NULL REFERENCES products(product_id),
    event_type          VARCHAR2(50),  -- view | click | add_to_cart | wishlist | purchase
    event_timestamp     TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    device_type         VARCHAR2(50),
    referrer            VARCHAR2(100),
    order_id            NUMBER(10) REFERENCES orders(order_id)
);

-- 6. REVIEWS TABLE
CREATE TABLE reviews (
    review_id           NUMBER(10) PRIMARY KEY,
    user_id             NUMBER(10) NOT NULL REFERENCES users(user_id),
    product_id          NUMBER(10) NOT NULL REFERENCES products(product_id),
    order_id            NUMBER(10) NOT NULL REFERENCES orders(order_id),
    rating              NUMBER(2),
    review_title        VARCHAR2(255),
    review_text         VARCHAR2(2000),
    review_date         TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    verified_purchase   NUMBER(1) DEFAULT 1,
    helpful_votes       NUMBER(6) DEFAULT 0
);

-- Sequences for web runtime creation of new entities
CREATE SEQUENCE seq_order_id START WITH 50000 INCREMENT BY 1;
CREATE SEQUENCE seq_order_item_id START WITH 50000 INCREMENT BY 1;
CREATE SEQUENCE seq_user_id START WITH 10000 INCREMENT BY 1;
CREATE SEQUENCE seq_interaction_id START WITH 1000000 INCREMENT BY 1;

-- Performance Indexes
CREATE INDEX idx_products_cat ON products(category);
CREATE INDEX idx_products_brand ON products(brand);
CREATE INDEX idx_products_active ON products(is_active);
CREATE INDEX idx_orders_user ON orders(user_id);
CREATE INDEX idx_order_items_ord ON order_items(order_id);
CREATE INDEX idx_order_items_prod ON order_items(product_id);
CREATE INDEX idx_inter_user ON interactions(user_id);
CREATE INDEX idx_inter_prod ON interactions(product_id);
CREATE INDEX idx_reviews_prod ON reviews(product_id);
