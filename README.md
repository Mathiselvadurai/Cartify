# Cartify

Cartify is a Flask e-commerce storefront backed by Oracle Database 26ai. It combines product catalog browsing, a shopping cart and simulated checkout with TF-IDF-based product search and similar-item recommendations.

## Features

- Browse products with category and gender filters, price and rating sorting, and pagination.
- Search products by matching queries against TF-IDF vectors built from product text fields.
- View content-based similar-product suggestions on product detail pages.
- Show fallback recommendations for guests or new users, based on highly rated and frequently purchased products.
- Register and sign in with passwords hashed using Werkzeug.
- Add products to a cart, change quantities, and remove items; the cart displays tax and shipping calculations.
- Apply the documented coupon codes <code>WELCOME10</code> (10% off) and <code>FESTIVE15</code> (15% off).
- Complete a simulated checkout with UPI, card, net banking, or cash-on-delivery options.
- View an order receipt, order tracking information, and order history.

## Technology

- Python and Flask
- Oracle Database 26ai with the Python <code>oracledb</code> driver in Thin mode
- scikit-learn, including <code>TfidfVectorizer</code> and cosine similarity
- Pandas and NumPy
- Bootstrap 5, Jinja2, HTML, CSS, and JavaScript

## Screenshots

Add screenshots captured from the running application before publishing. The paths below are placeholders; commit the real image files and uncomment or update the links when they are available.

<!--
![Cartify home page](docs/screenshots/home.png)
![Product catalog](docs/screenshots/catalog.png)
![Product details and recommendations](docs/screenshots/product-detail.png)
![Cart and checkout](docs/screenshots/cart-checkout.png)
-->

## Requirements

The project documentation specifies:

- Python 3.11 or newer. Python 3.14 is recommended in the original documentation; confirm compatibility with the project's dependencies before choosing it.
- Oracle Database 26ai Free, available locally on port <code>1521</code> with service name <code>FREEPDB1</code>.

## Setup

From the project root, create and activate a virtual environment, then install the dependencies:

~~~powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
~~~

Start Oracle and make sure it is reachable using the connection settings expected by the application. The project includes <code>scripts/oracle_schema.sql</code> for the schema and <code>scripts/import_data_to_oracle.py</code> for importing CSV data. Review those files for the required Oracle setup, configuration values, and execution order; those details are not documented here.

Then start the application:

~~~powershell
python run.py
~~~

Open [http://127.0.0.1:5000](http://127.0.0.1:5000) in a browser.

## Configuration and secrets

The required environment-variable names and formats are not documented here. Check <code>.env.example</code>, <code>app/db.py</code>, and the Flask application configuration for the exact settings before creating a local <code>.env</code>. Do not guess variable names or commit real credentials or secret keys.

Keep local secrets out of Git. A suitable <code>.gitignore</code> baseline is:

~~~gitignore
# Local secrets
.env
.env.*
!.env.example

# Python environments and generated files
.venv/
venv/
__pycache__/
*.py[cod]
.pytest_cache/
*.log
~~~

Review <code>.env.example</code> before publishing it: it should contain only documented variable names and safe placeholder values.

## Recommendation approach

Cartify uses a content-based recommendation engine. It combines product fields such as name, brand, category, subcategory, product type, color, gender, search keywords, and description into text for TF-IDF vectorization. Cosine similarity ranks related products and search results.

The project documentation describes a fallback for guests and new users using highly rated and best-selling products. No collaborative-filtering implementation is documented here.

## Database

The project documentation lists Oracle tables for products, users, orders, order items, interactions, and reviews, along with sequences for order, order-item, user, and interaction IDs. It describes checkout as creating order records, updating stock, and recording purchase interactions in a transaction.

See <code>scripts/oracle_schema.sql</code> and <code>app/db.py</code> for the schema and connection implementation. Confirm the table names, sequence names, transaction behavior, and connection mode against the code before relying on them.

## Project structure

The GitHub repository contains the Cartify application and its supporting files:

~~~text
Cartify/
├── app/
│   ├── routes/
│   ├── services/
│   ├── static/
│   └── templates/
├── evidence/
│   └── screenshots/
├── scripts/
├── tests/
├── .env.example
├── .gitignore
├── README.md
├── requirements.txt
└── run.py
~~~

The large source datasets are not included in this repository. To import products and sample records, provide the required CSV files under <code>data/raw/</code> after confirming that you have permission to use them. The separate train-booking <code>backend/</code> and <code>frontend/</code> folders, along with local files such as <code>.env</code>, <code>.venv/</code>, <code>backups/</code>, and <code>scratch/</code>, are not part of this GitHub upload.

## Tests

The project folder contains a <code>tests/</code> directory, but no test command or reproducible test results are documented here. Check the test files and project configuration for the correct command.




