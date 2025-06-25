import streamlit as st
import datetime
import uuid
import sqlite3
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# --- Streamlit Page Configuration (MUST BE THE FIRST STREAMLIT COMMAND) ---
st.set_page_config(
    page_title="Shumba Credit Manager",
    page_icon="💰",
    layout="wide"
)

st.title("CHARUMBIRA CREDIT_TRACK")

# --- SQLite Database Initialization ---
DB_NAME = 'charumbira_loans.db'

def init_db():
    """Initializes the SQLite database and creates tables if they don't exist."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    # Create borrowers table (added cooperate_number and phone_number)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS borrowers (
            borrower_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            address TEXT,
            id_number TEXT UNIQUE NOT NULL,
            payslip_info TEXT,
            cooperate_number TEXT,
            phone_number TEXT -- New column
        )
    ''')

    # Create loans table (added notification flags)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS loans (
            loan_id TEXT PRIMARY KEY,
            borrower_id TEXT NOT NULL,
            amount REAL NOT NULL,
            interest_rate REAL NOT NULL,
            loan_date TEXT NOT NULL,
            due_date TEXT NOT NULL,
            initial_total_due REAL NOT NULL,
            current_outstanding_balance REAL NOT NULL,
            payments_made REAL NOT NULL,
            status TEXT NOT NULL,
            notification_due_soon_sent INTEGER DEFAULT 0, -- 0 for False, 1 for True
            notification_overdue_sent INTEGER DEFAULT 0, -- 0 for False, 1 for True
            FOREIGN KEY (borrower_id) REFERENCES borrowers(borrower_id)
        )
    ''')

    # Add new columns to existing tables if they don't exist
    try:
        cursor.execute("ALTER TABLE borrowers ADD COLUMN cooperate_number TEXT")
        conn.commit()
    except sqlite3.OperationalError:
        pass # Column already exists

    try:
        cursor.execute("ALTER TABLE borrowers ADD COLUMN phone_number TEXT") # New ALTER TABLE for phone_number
        conn.commit()
    except sqlite3.OperationalError:
        pass # Column already exists

    try:
        cursor.execute("ALTER TABLE loans ADD COLUMN notification_due_soon_sent INTEGER DEFAULT 0")
        conn.commit()
    except sqlite3.OperationalError:
        pass # Column already exists

    try:
        cursor.execute("ALTER TABLE loans ADD COLUMN notification_overdue_sent INTEGER DEFAULT 0")
        conn.commit()
    except sqlite3.OperationalError:
        pass # Column already exists

    conn.commit()
    conn.close()

# Initialize the database on application startup
init_db()

# --- Email Configuration (UPDATE THESE VALUES) ---
# IMPORTANT: For security, DO NOT hardcode sensitive information like passwords in production apps.
# Use Streamlit Secrets (st.secrets) or environment variables for deployment.
SENDER_EMAIL = "your_email@example.com"  # Replace with your sending email address
SENDER_PASSWORD = "your_email_password" # Replace with your email password or App Password (for Gmail)
SMTP_SERVER = "smtp.gmail.com" # Or your email provider's SMTP server
SMTP_PORT = 587 # Typically 587 for TLS, 465 for SSL

# --- Helper Functions for Loan Calculations and Status ---
def calculate_initial_due(amount, interest_rate):
    """Calculates the total amount due initially, including interest."""
    return amount * (1 + interest_rate)

def calculate_new_due_after_payment(outstanding_balance, interest_rate):
    """
    Recalculates the new total due based on the remaining outstanding balance
    after a payment, applying the interest for the next period.
    """
    return outstanding_balance * (1 + interest_rate)

def get_loan_status(loan):
    """Determines the current status of a loan based on its due date and balance."""
    today = datetime.date.today()
    # Convert string date to datetime.date object for comparison
    due_date = datetime.datetime.strptime(loan['due_date'], '%Y-%m-%d').date()

    if loan['current_outstanding_balance'] <= 0.01: # Check for near zero for floating point precision
        return "Paid"
    elif today > due_date:
        return "Overdue"
    elif (due_date - today).days <= 3 and loan['current_outstanding_balance'] > 0:
        return "Due Soon"
    else:
        return "Active"

# --- Email Sending Function ---
def send_email(recipient_email, subject, body):
    """Sends an email notification."""
    try:
        msg = MIMEMultipart()
        msg['From'] = SENDER_EMAIL
        msg['To'] = recipient_email
        msg['Subject'] = subject
        msg.attach(MIMEText(body, 'plain'))

        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls() # Secure the connection
            server.login(SENDER_EMAIL, SENDER_PASSWORD)
            server.send_message(msg)
        return True
    except smtplib.SMTPAuthenticationError:
        st.error("Email sending failed: Authentication error. Check your SENDER_EMAIL and SENDER_PASSWORD. For Gmail, you might need an 'App password' if 2FA is enabled.")
        return False
    except smtplib.SMTPConnectError:
        st.error("Email sending failed: Could not connect to SMTP server. Check SMTP_SERVER and SMTP_PORT, or your internet connection.")
        return False
    except Exception as e:
        st.error(f"Email sending failed: {e}")
        return False

# --- SQLite Data Management Functions ---

def fetch_borrowers():
    """Fetches all borrowers from SQLite and stores them in session state."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    # Select all columns, including the new 'phone_number'
    cursor.execute("SELECT borrower_id, name, address, id_number, payslip_info, cooperate_number, phone_number FROM borrowers")
    borrowers_data = cursor.fetchall()
    conn.close()
    
    borrowers = {}
    # Unpack all 7 values
    for b_id, name, address, id_num, payslip, cooperate_num, phone_num in borrowers_data:
        borrowers[b_id] = {
            "name": name,
            "address": address,
            "id_number": id_num,
            "payslip_info": payslip,
            "cooperate_number": cooperate_num,
            "phone_number": phone_num, # Include new field
            "borrower_id": b_id
        }
    st.session_state.borrowers = borrowers
    return st.session_state.borrowers

def add_borrower_to_db(borrower_data):
    """Adds a new borrower to SQLite."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO borrowers (borrower_id, name, address, id_number, payslip_info, cooperate_number, phone_number) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (borrower_data['borrower_id'], borrower_data['name'], borrower_data['address'],
             borrower_data['id_number'], borrower_data['payslip_info'], borrower_data['cooperate_number'],
             borrower_data['phone_number']) # Include new field
        )
        conn.commit()
        st.success(f"Borrower '{borrower_data['name']}' saved to database.")
        fetch_borrowers()
        return True
    except sqlite3.IntegrityError:
        st.error(f"Error: Borrower with ID Number '{borrower_data['id_number']}' already exists.")
        return False
    except Exception as e:
        st.error(f"Error adding borrower to SQLite: {e}")
        return False
    finally:
        conn.close()

def update_borrower_in_db(borrower_id, updated_data):
    """Updates an existing borrower in SQLite."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    try:
        set_clauses = [f"{key} = ?" for key in updated_data.keys()]
        query = f"UPDATE borrowers SET {', '.join(set_clauses)} WHERE borrower_id = ?"
        values = list(updated_data.values()) + [borrower_id]

        cursor.execute(query, values)
        conn.commit()
        st.success(f"Borrower '{borrower_id[:8]}...' updated in database.")
        fetch_borrowers() # Refresh session state after updating
        return True
    except sqlite3.IntegrityError:
        st.error(f"Error: ID Number '{updated_data.get('id_number')}' already exists for another borrower.")
        return False
    except Exception as e:
        st.error(f"Error updating borrower in SQLite: {e}")
        return False
    finally:
        conn.close()

def fetch_loans():
    """Fetches all loans from SQLite and stores them in session state."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT loan_id, borrower_id, amount, interest_rate, loan_date, due_date, "
        "initial_total_due, current_outstanding_balance, payments_made, status, "
        "notification_due_soon_sent, notification_overdue_sent FROM loans"
    )
    loans_data = cursor.fetchall()
    conn.close()

    loans = []
    for l_id, b_id, amt, rate, l_date, d_date, init_due, current_bal, payments, status, due_soon_sent, overdue_sent in loans_data:
        loans.append({
            "loan_id": l_id,
            "borrower_id": b_id,
            "amount": amt,
            "interest_rate": rate,
            "loan_date": l_date,
            "due_date": d_date,
            "initial_total_due": init_due,
            "current_outstanding_balance": current_bal,
            "payments_made": payments,
            "status": status,
            "notification_due_soon_sent": bool(due_soon_sent), # Convert to boolean
            "notification_overdue_sent": bool(overdue_sent) # Convert to boolean
        })
    st.session_state.loans = loans
    return st.session_state.loans

def add_loan_to_db(loan_data):
    """Adds a new loan to SQLite."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO loans (loan_id, borrower_id, amount, interest_rate, loan_date, due_date, "
            "initial_total_due, current_outstanding_balance, payments_made, status, "
            "notification_due_soon_sent, notification_overdue_sent) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (loan_data['loan_id'], loan_data['borrower_id'], loan_data['amount'],
             loan_data['interest_rate'], loan_data['loan_date'], loan_data['due_date'],
             loan_data['initial_total_due'], loan_data['current_outstanding_balance'],
             loan_data['payments_made'], loan_data['status'],
             int(loan_data['notification_due_soon_sent']), int(loan_data['notification_overdue_sent'])) # Convert bool to int
        )
        conn.commit()
        st.success(f"Loan '{loan_data['loan_id'][:8]}...' saved to database.")
        fetch_loans()
        return True
    except Exception as e:
        st.error(f"Error adding loan to SQLite: {e}")
        return False
    finally:
        conn.close()

def update_loan_in_db(loan_id, updated_data):
    """Updates an existing loan in SQLite."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    try:
        # Prepare data for update, converting booleans to integers
        data_to_update = {k: int(v) if isinstance(v, bool) else v for k, v in updated_data.items()}
        
        set_clauses = [f"{key} = ?" for key in data_to_update.keys()]
        query = f"UPDATE loans SET {', '.join(set_clauses)} WHERE loan_id = ?"
        values = list(data_to_update.values()) + [loan_id]

        cursor.execute(query, values)
        conn.commit()
        st.success(f"Loan '{loan_id[:8]}...' updated in database.")
        fetch_loans()
        return True
    except Exception as e:
        st.error(f"Error updating loan in SQLite: {e}")
        return False
    finally:
        conn.close()

def add_repayment_to_db(repayment_data):
    """Adds a new repayment record to SQLite."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO repayments (repayment_id, loan_id, amount_paid, repayment_date) VALUES (?, ?, ?, ?)",
            (repayment_data['repayment_id'], repayment_data['loan_id'],
             repayment_data['amount_paid'], repayment_data['repayment_date'])
        )
        conn.commit()
        st.success(f"Repayment recorded for loan '{repayment_data['loan_id'][:8]}...'.")
        return True
    except Exception as e:
        st.error(f"Error adding repayment to SQLite: {e}")
        return False
    finally:
        conn.close()

# Initialize session state variables and fetch data on startup
if 'borrowers' not in st.session_state:
    st.session_state.borrowers = {}
if 'loans' not in st.session_state:
    st.session_state.loans = []
if 'repayments' not in st.session_state:
    st.session_state.repayments = []

# Fetch initial data from SQLite
fetch_borrowers()
fetch_loans()


# --- UI Functions for each page ---

def loan_management_main():
    """Main function for managing borrowers and loans."""
    st.header("Loan and Borrower Management")
    
    management_type = st.radio("Select an action:", ["Register Borrower", "Create Loan"], horizontal=True)

    if management_type == "Register Borrower":
        st.subheader("Register New Borrower")
        with st.form("borrower_form"):
            st.write("Fill in the details for the new borrower.")
            name = st.text_input("Full Name", help="Enter the borrower's full name.")
            address = st.text_area("Address", help="Enter the borrower's residential address.")
            id_number = st.text_input("ID Number", help="Enter the borrower's identification number.")
            cooperate_number = st.text_input("Cooperate Number (Optional)", help="Enter the borrower's cooperate number, if applicable.")
            phone_number = st.text_input("Phone Number (Optional)", help="Enter the borrower's phone number.") # New input field
            payslip = st.file_uploader("Upload Payslip (Optional)", type=["pdf", "jpg", "png"],
                                    help="Upload a payslip document (PDF, JPG, PNG).")
            submit_button = st.form_submit_button("Register Borrower")

            if submit_button:
                if name and address and id_number:
                    borrower_id = str(uuid.uuid4())
                    borrower_data = {
                        "borrower_id": borrower_id,
                        "name": name,
                        "address": address,
                        "id_number": id_number,
                        "payslip_info": payslip.name if payslip else "No payslip uploaded",
                        "cooperate_number": cooperate_number,
                        "phone_number": phone_number # Save new field
                    }
                    add_borrower_to_db(borrower_data)
                else:
                    st.error("Please fill in all required fields (Full Name, Address, ID Number).")

    elif management_type == "Create Loan":
        st.subheader("Create New Loan")
        if not st.session_state.borrowers:
            st.info("No borrowers registered yet. Please register a borrower first to create a loan.")
            return

        borrower_options = {b['name']: bid for bid, b in st.session_state.borrowers.items()}

        with st.form("loan_form"):
            st.write("Provide details for the new loan.")
            selected_borrower_name = st.selectbox(
                "Select Borrower",
                options=list(borrower_options.keys()),
                help="Choose the borrower for this loan."
            )
            amount = st.number_input("Loan Amount ($)", min_value=0.01, format="%.2f",
                                    help="Enter the principal amount of the loan.")
            loan_date = st.date_input("Loan Date", value=datetime.date.today(),
                                    help="Select the date when the loan was issued.")

            submit_button = st.form_submit_button("Create Loan")

            if submit_button:
                if selected_borrower_name and amount > 0:
                    borrower_id = borrower_options[selected_borrower_name]
                    loan_id = str(uuid.uuid4())
                    interest_rate = 0.20
                    initial_total_due = calculate_initial_due(amount, interest_rate)
                    due_date = loan_date + datetime.timedelta(days=30)

                    new_loan = {
                        "loan_id": loan_id,
                        "borrower_id": borrower_id,
                        "amount": amount,
                        "interest_rate": interest_rate,
                        "loan_date": loan_date.strftime('%Y-%m-%d'),
                        "due_date": due_date.strftime('%Y-%m-%d'),
                        "initial_total_due": initial_total_due,
                        "current_outstanding_balance": initial_total_due,
                        "payments_made": 0.0,
                        "status": "Active",
                        "notification_due_soon_sent": False,
                        "notification_overdue_sent": False
                    }
                    add_loan_to_db(new_loan)
                else:
                    st.error("Please select a borrower and enter a valid loan amount.")


def record_payment():
    """Displays a form to record a payment for an existing loan."""
    st.header("Record Loan Payment")

    if not st.session_state.loans:
        st.info("No active loans to record payments for.")
        return

    active_loans_for_payment = [loan for loan in st.session_state.loans if loan['current_outstanding_balance'] > 0.01]

    if not active_loans_for_payment:
        st.info("All loans are fully paid or none exist.")
        return

    loan_options = {
        f"Loan ID: {loan['loan_id'][:8]}... - Borrower: {st.session_state.borrowers.get(loan['borrower_id'], {}).get('name', 'N/A')} - Outstanding: ${loan['current_outstanding_balance']:.2f}": loan['loan_id']
        for loan in active_loans_for_payment
    }

    with st.form("payment_form"):
        st.write("Enter details for the payment.")
        selected_loan_display = st.selectbox(
            "Select Loan to Pay",
            options=list(loan_options.keys()),
            help="Choose the loan to record a payment against."
        )
        payment_amount = st.number_input("Payment Amount ($)", min_value=0.01, format="%.2f",
                                         help="Enter the amount received for this payment.")
        payment_date = st.date_input("Payment Date", value=datetime.date.today(),
                                     help="Select the date when the payment was made.")

        submit_button = st.form_submit_button("Record Payment")

        if submit_button:
            selected_loan_id = loan_options[selected_loan_display]
            for loan in st.session_state.loans:
                if loan['loan_id'] == selected_loan_id:
                    original_outstanding = loan['current_outstanding_balance']
                    if payment_amount > original_outstanding:
                        st.warning(f"Payment amount ${payment_amount:,.2f} exceeds outstanding balance ${original_outstanding:,.2f}. "
                                   "Adjusting payment to cover the remaining balance.")
                        payment_amount = original_outstanding

                    loan['payments_made'] += payment_amount
                    loan['current_outstanding_balance'] -= payment_amount

                    # Reset notification flags if payment changes status significantly
                    # For simplicity, we reset both on any payment. More complex logic could be applied.
                    loan['notification_due_soon_sent'] = False
                    loan['notification_overdue_sent'] = False

                    if loan['current_outstanding_balance'] > 0.01:
                        loan['current_outstanding_balance'] = calculate_new_due_after_payment(
                            loan['current_outstanding_balance'], loan['interest_rate']
                        )
                        st.info(f"New outstanding balance (including 20% interest for next period): ${loan['current_outstanding_balance']:,.2f}")
                    else:
                        loan['current_outstanding_balance'] = 0.0

                    loan['status'] = get_loan_status(loan)

                    # Update loan in SQLite
                    update_loan_in_db(loan['loan_id'], {
                        "payments_made": loan['payments_made'],
                        "current_outstanding_balance": loan['current_outstanding_balance'],
                        "status": loan['status'],
                        "notification_due_soon_sent": loan['notification_due_soon_sent'],
                        "notification_overdue_sent": loan['notification_overdue_sent']
                    })

                    # Record repayment history in SQLite
                    add_repayment_to_db({
                        "repayment_id": str(uuid.uuid4()),
                        "loan_id": selected_loan_id,
                        "amount_paid": payment_amount,
                        "repayment_date": payment_date.strftime('%Y-%m-%d')
                    })

                    st.success(f"Payment of ${payment_amount:,.2f} recorded for loan {selected_loan_id[:8]}.... "
                               f"Current Outstanding: ${loan['current_outstanding_balance']:,.2f}")
                    break
            else:
                st.error("Error: Loan not found. Please select a valid loan.")

def view_loans():
    """Displays a table of all loans with filtering, sorting, and summary statistics."""
    st.header("All Loans")

    # Refresh data from SQLite just in case
    fetch_loans()
    fetch_borrowers()

    if not st.session_state.loans:
        st.info("No loans created yet.")
        return

    # Separate active/outstanding loans from paid loans
    active_outstanding_loans = [loan for loan in st.session_state.loans if get_loan_status(loan) != "Paid"]
    paid_loans = [loan for loan in st.session_state.loans if get_loan_status(loan) == "Paid"]

    st.subheader("Active and Outstanding Loans")
    display_active_loans = [] # Initialize as empty list
    if active_outstanding_loans:
        for loan in active_outstanding_loans:
            borrower_name = st.session_state.borrowers.get(loan['borrower_id'], {}).get('name', 'N/A')
            current_status = get_loan_status(loan)
            display_active_loans.append({
                "Loan ID": loan['loan_id'][:8] + "...",
                "Borrower": borrower_name,
                "Original Amount": f"${loan['amount']:,.2f}",
                "Loan Date": loan['loan_date'],
                "Original Due Date": loan['due_date'],
                "Initial Total Due": f"${loan['initial_total_due']:,.2f}",
                "Payments Made": f"${loan['payments_made']:,.2f}",
                "Current Outstanding": f"${loan['current_outstanding_balance']:,.2f}",
                "Status": current_status
            })
        st.dataframe(display_active_loans, use_container_width=True, hide_index=True)
    else:
        st.info("No active or outstanding loans.")

    st.subheader("Paid Loans")
    display_paid_loans = [] # Initialize as empty list
    if paid_loans:
        for loan in paid_loans:
            borrower_name = st.session_state.borrowers.get(loan['borrower_id'], {}).get('name', 'N/A')
            display_paid_loans.append({
                "Loan ID": loan['loan_id'][:8] + "...",
                "Borrower": borrower_name,
                "Original Amount": f"${loan['amount']:,.2f}",
                "Loan Date": loan['loan_date'],
                "Original Due Date": loan['due_date'],
                "Initial Total Due": f"${loan['initial_total_due']:,.2f}",
                "Payments Made": f"${loan['payments_made']:,.2f}",
                "Current Outstanding": f"${loan['current_outstanding_balance']:,.2f}",
                "Status": "Paid"
            })
        st.dataframe(display_paid_loans, use_container_width=True, hide_index=True)
    else:
        st.info("No loans have been fully paid yet.")

    st.subheader("Filter and Sort Loans (Applies to all loans)")
    col1, col2, col3 = st.columns(3)
    with col1:
        status_filter = st.selectbox("Filter by Status", ["All", "Active", "Due Soon", "Overdue", "Paid"],
                                     help="Filter loans by their current payment status.")
    with col2:
        sort_by = st.selectbox("Sort By", ["Loan Date", "Original Due Date", "Current Outstanding"],
                               help="Choose a column to sort the loans by.")
    with col3:
        sort_order = st.radio("Order", ["Ascending", "Descending"], horizontal=True,
                              help="Select the sorting order (ascending or descending).")

    # Apply filter and sort to the combined list for the "Filtered and Sorted Loan List" section
    combined_loans_for_filter = display_active_loans + display_paid_loans
    filtered_loans = [loan for loan in combined_loans_for_filter if status_filter == "All" or loan["Status"] == status_filter]

    if sort_by == "Loan Date":
        filtered_loans.sort(key=lambda x: datetime.datetime.strptime(x["Loan Date"], '%Y-%m-%d'),
                            reverse=(sort_order == "Descending"))
    elif sort_by == "Original Due Date":
        filtered_loans.sort(key=lambda x: datetime.datetime.strptime(x["Original Due Date"], '%Y-%m-%d'),
                            reverse=(sort_order == "Descending"))
    elif sort_by == "Current Outstanding":
        filtered_loans.sort(key=lambda x: float(x["Current Outstanding"].replace('$', '').replace(',', '')),
                            reverse=(sort_order == "Descending"))

    st.write("### Filtered and Sorted Loan List")
    if filtered_loans:
        st.dataframe(filtered_loans, use_container_width=True, hide_index=True)
    else:
        st.info("No loans match the current filter criteria.")

    st.subheader("Summary Statistics")
    total_loans = len(st.session_state.loans)
    total_amount_lent = sum(loan['amount'] for loan in st.session_state.loans)
    total_outstanding = sum(loan['current_outstanding_balance'] for loan in st.session_state.loans if get_loan_status(loan) != "Paid")
    total_payments_received = sum(loan['payments_made'] for loan in st.session_state.loans)

    col_sum1, col_sum2, col_sum3, col_sum4 = st.columns(4)
    with col_sum1:
        st.metric("Total Loans Issued", total_loans)
    with col_sum2:
        st.metric("Total Principal Lent", f"${total_amount_lent:,.2f}")
    with col_sum3:
        st.metric("Total Current Outstanding", f"${total_outstanding:,.2f}")
    with col_sum4:
        st.metric("Total Payments Received", f"${total_payments_received:,.2f}")


def view_borrowers():
    """Displays a table of all registered borrowers."""
    st.header("All Registered Borrowers")

    fetch_borrowers()

    if not st.session_state.borrowers:
        st.info("No borrowers registered yet.")
        return

    display_borrowers = []
    for borrower_id, borrower_data in st.session_state.borrowers.items():
        display_borrowers.append({
            "Borrower ID": borrower_id[:8] + "...",
            "Full Name": borrower_data.get('name', 'N/A'),
            "Address": borrower_data.get('address', 'N/A'),
            "ID Number": borrower_data.get('id_number', 'N/A'),
            "Cooperate Number": borrower_data.get('cooperate_number', 'N/A'),
            "Phone Number": borrower_data.get('phone_number', 'N/A'), # Display new field
            "Payslip Info": borrower_data.get('payslip_info', 'N/A')
        })
    
    st.subheader("Client Details")
    st.dataframe(display_borrowers, use_container_width=True, hide_index=True)


def edit_borrower_form():
    """Form to edit details of an existing borrower."""
    fetch_borrowers() # Ensure latest borrowers are fetched
    
    if not st.session_state.borrowers:
        st.info("No borrowers available to edit.")
        return

    borrower_display_options = {
        f"Borrower: {b['name']} (ID: {b['borrower_id'][:8]}...)": b['borrower_id']
        for b in st.session_state.borrowers.values()
    }

    selected_borrower_display = st.selectbox(
        "Select Borrower to Edit",
        options=list(borrower_display_options.keys()),
        index=0 if borrower_display_options else None,
        format_func=lambda x: x
    )

    if selected_borrower_display:
        selected_borrower_id = borrower_display_options[selected_borrower_display]
        current_borrower = st.session_state.borrowers.get(selected_borrower_id)

        if current_borrower:
            st.subheader(f"Editing Borrower: {current_borrower['name']} (ID: {selected_borrower_id[:8]}...)")
            
            with st.form("edit_borrower_form", clear_on_submit=False):
                edited_name = st.text_input("Full Name", value=current_borrower.get('name', ''))
                edited_address = st.text_area("Address", value=current_borrower.get('address', ''))
                edited_id_number = st.text_input("ID Number", value=current_borrower.get('id_number', ''))
                edited_cooperate_number = st.text_input("Cooperate Number (Optional)", value=current_borrower.get('cooperate_number', ''))
                edited_phone_number = st.text_input("Phone Number (Optional)", value=current_borrower.get('phone_number', '')) # New input field
                
                st.write(f"Current Payslip Info: {current_borrower.get('payslip_info', 'No payslip uploaded')}")

                edit_submit_button = st.form_submit_button("Update Borrower Details")

                if edit_submit_button:
                    updated_data = {
                        "name": edited_name,
                        "address": edited_address,
                        "id_number": edited_id_number,
                        "cooperate_number": edited_cooperate_number,
                        "phone_number": edited_phone_number, # Update new field
                    }
                    if update_borrower_in_db(selected_borrower_id, updated_data):
                        st.success("Borrower details updated successfully!")
                        st.experimental_rerun()
                    else:
                        st.error("Failed to update borrower details.")
        else:
            st.error("Selected borrower not found in current data.")


def edit_loan_form():
    """Form to edit details of an existing loan."""
    st.header("Edit Loan Details")

    fetch_loans() # Ensure latest loans are fetched
    
    if not st.session_state.loans:
        st.info("No loans available to edit.")
        return

    loan_display_options = {
        f"Loan ID: {loan['loan_id'][:8]}... - Borrower: {st.session_state.borrowers.get(loan['borrower_id'], {}).get('name', 'N/A')} - Original Amount: ${loan['amount']:.2f}": loan['loan_id']
        for loan in st.session_state.loans
    }

    selected_loan_display = st.selectbox(
        "Select Loan to Edit",
        options=list(loan_display_options.keys()),
        index=0 if loan_display_options else None,
        format_func=lambda x: x
    )

    if selected_loan_display:
        selected_loan_id = loan_display_options[selected_loan_display]
        current_loan = next((loan for loan in st.session_state.loans if loan['loan_id'] == selected_loan_id), None)

        if current_loan:
            st.subheader(f"Editing Loan: {selected_loan_id[:8]}... (Borrower: {st.session_state.borrowers.get(current_loan['borrower_id'], {}).get('name', 'N/A')})")
            
            with st.form("edit_loan_form", clear_on_submit=False):
                current_loan_date = datetime.datetime.strptime(current_loan['loan_date'], '%Y-%m-%d').date()
                current_due_date = datetime.datetime.strptime(current_loan['due_date'], '%Y-%m-%d').date()

                edited_amount = st.number_input("Loan Amount ($)", value=current_loan['amount'], min_value=0.01, format="%.2f")
                edited_loan_date = st.date_input("Loan Date", value=current_loan_date)
                edited_due_date = st.date_input("Due Date", value=current_due_date)

                edit_submit_button = st.form_submit_button("Update Loan Details")

                if edit_submit_button:
                    new_initial_total_due = calculate_initial_due(edited_amount, current_loan['interest_rate'])
                    principal_change = edited_amount - current_loan['amount']
                    new_current_outstanding_balance = current_loan['current_outstanding_balance'] + principal_change
                    if new_current_outstanding_balance < 0:
                        new_current_outstanding_balance = 0.0

                    updated_data = {
                        "amount": edited_amount,
                        "loan_date": edited_loan_date.strftime('%Y-%m-%d'),
                        "due_date": edited_due_date.strftime('%Y-%m-%d'),
                        "initial_total_due": new_initial_total_due,
                        "current_outstanding_balance": new_current_outstanding_balance,
                        "status": get_loan_status({
                            'due_date': edited_due_date.strftime('%Y-%m-%d'),
                            'current_outstanding_balance': new_current_outstanding_balance
                        }),
                        "notification_due_soon_sent": False,
                        "notification_overdue_sent": False
                    }
                    if update_loan_in_db(selected_loan_id, updated_data):
                        st.success("Loan details updated successfully!")
                        st.experimental_rerun()
                    else:
                        st.error("Failed to update loan details.")
        else:
            st.error("Selected loan not found in current data.")


def edit_main():
    """Main function for the combined Edit page."""
    st.header("Edit Details")
    edit_type = st.radio("What would you like to edit?", ["Loan", "Borrower"], horizontal=True)

    if edit_type == "Loan":
        edit_loan_form()
    elif edit_type == "Borrower":
        edit_borrower_form()


def delete_loan():
    """Allows user to delete an existing loan and its associated repayments."""
    st.header("Delete Loan")

    fetch_loans() # Ensure latest loans are fetched

    if not st.session_state.loans:
        st.info("No loans available to delete.")
        return

    loan_display_options = {
        f"Loan ID: {loan['loan_id'][:8]}... - Borrower: {st.session_state.borrowers.get(loan['borrower_id'], {}).get('name', 'N/A')} - Status: {get_loan_status(loan)}": loan['loan_id']
        for loan in st.session_state.loans
    }

    with st.form("delete_loan_form"):
        selected_loan_display = st.selectbox(
            "Select Loan to Delete",
            options=list(loan_display_options.keys()),
            index=0 if loan_display_options else None,
            format_func=lambda x: x
        )
        st.warning("🚨 **Warning:** Deleting a loan will also remove all its associated repayment records. This action cannot be undone.")
        confirm_delete = st.checkbox("I understand and confirm that I want to delete this loan and its repayments.")
        delete_button = st.form_submit_button("Delete Selected Loan")

        if delete_button:
            if selected_loan_display and confirm_delete:
                selected_loan_id = loan_display_options[selected_loan_display]
                conn = sqlite3.connect(DB_NAME)
                cursor = conn.cursor()
                try:
                    # Delete associated repayments first to satisfy foreign key constraints
                    cursor.execute("DELETE FROM repayments WHERE loan_id = ?", (selected_loan_id,))
                    # Then delete the loan
                    cursor.execute("DELETE FROM loans WHERE loan_id = ?", (selected_loan_id,))
                    conn.commit()
                    st.success(f"Loan {selected_loan_id[:8]}... and its repayments deleted successfully!")
                    fetch_loans() # Refresh session state
                    st.experimental_rerun() # Rerun to update selectbox and display
                except Exception as e:
                    st.error(f"Error deleting loan: {e}")
                finally:
                    conn.close()
            elif not confirm_delete:
                st.error("Please confirm deletion by checking the box.")


def notifications():
    """Displays notifications for loans that are due soon or overdue and sends emails."""
    st.header("Payment Notifications")

    fetch_loans()
    fetch_borrowers()

    today = datetime.date.today()
    found_notifications = False
    
    # Define the recipient email for notifications
    NOTIFICATION_RECIPIENT_EMAIL = "gpadiel88@gmail.com" # The email address to send notifications to

    if not st.session_state.loans:
        st.info("No loans created yet to check for notifications.")
        return

    st.write("Here are your current loan payment alerts:")

    for loan in st.session_state.loans:
        if loan['current_outstanding_balance'] > 0.01:
            due_date = datetime.datetime.strptime(loan['due_date'], '%Y-%m-%d').date()
            borrower_name = st.session_state.borrowers.get(loan['borrower_id'], {}).get('name', 'N/A')

            if today > due_date:
                st.error(f"🚨 **OVERDUE!** Loan ID: **{loan['loan_id'][:8]}...** for **{borrower_name}** is **{ (today - due_date).days } days overdue!** "
                         f"Original due: {loan['due_date']}. Outstanding: **${loan['current_outstanding_balance']:,.2f}**")
                found_notifications = True

                # Send email if not already sent for this overdue status
                if not loan['notification_overdue_sent']:
                    subject = f"OVERDUE LOAN ALERT: Loan for {borrower_name} (ID: {loan['loan_id'][:8]}...)"
                    body = (
                        f"Dear Administrator,\n\n"
                        f"This is an urgent notification. The loan for {borrower_name} "
                        f"(Loan ID: {loan['loan_id']}) is { (today - due_date).days } days OVERDUE.\n"
                        f"Original Due Date: {loan['due_date']}\n"
                        f"Current Outstanding Balance: ${loan['current_outstanding_balance']:,.2f}\n\n"
                        f"Please take appropriate action."
                    )
                    if send_email(NOTIFICATION_RECIPIENT_EMAIL, subject, body):
                        update_loan_in_db(loan['loan_id'], {"notification_overdue_sent": True})
                    else:
                        st.warning("Failed to send overdue email notification. Check email credentials and settings.")

            elif (due_date - today).days <= 3:
                st.warning(f"⚠️ **DUE SOON!** Loan ID: **{loan['loan_id'][:8]}...** for **{borrower_name}** is due on **{loan['due_date']}** (in {(due_date - today).days} days). "
                           f"Outstanding: **${loan['current_outstanding_balance']:,.2f}**")
                found_notifications = True

                # Send email if not already sent for this due soon status
                if not loan['notification_due_soon_sent']:
                    subject = f"LOAN DUE SOON: Loan for {borrower_name} (ID: {loan['loan_id'][:8]}...)"
                    body = (
                        f"Dear Administrator,\n\n"
                        f"This is a reminder that the loan for {borrower_name} "
                        f"(Loan ID: {loan['loan_id']}) is due on {loan['due_date']} (in {(due_date - today).days} days).\n"
                        f"Current Outstanding Balance: ${loan['current_outstanding_balance']:,.2f}\n\n"
                        f"Please follow up with the borrower."
                    )
                    if send_email(NOTIFICATION_RECIPIENT_EMAIL, subject, body):
                        update_loan_in_db(loan['loan_id'], {"notification_due_soon_sent": True})
                    else:
                        st.warning("Failed to send 'due soon' email notification. Check email credentials and settings.")
            else:
                # If a loan is active and not due soon/overdue, ensure flags are reset if they were previously true
                # This handles cases where a loan might have been due soon, then paid down, then becomes due soon again later
                if loan['notification_due_soon_sent'] or loan['notification_overdue_sent']:
                    update_loan_in_db(loan['loan_id'], {
                        "notification_due_soon_sent": False,
                        "notification_overdue_sent": False
                    })


    if not found_notifications:
        st.info("✅ No urgent payment notifications at this time. All active loans are either within their payment window or fully paid.")


with st.sidebar:
    st.header("Navigation")

    page = st.radio(
        "Go to",
        ["Home", "Loan Management", "Record Payment", "View Loans", "View Borrowers", "Edit", "Delete Loan", "Notifications"],
        help="Select a page to navigate the application."
    )
    st.markdown("---")
    st.markdown("**About Data Persistence:**")
    st.info("This application uses **SQLite** for persistent data storage. "
            "Your borrower, loan, and repayment data will be saved in a local file named 'charumbira_loans.db'.")
    st.markdown("---")
    st.markdown("Developed by gpadiel88@gmail.com")

# Render the selected page based on user's sidebar choice
if page == "Home":
    st.header("PACE LOANS")
    st.write("Use the sidebar to navigate through the different functionalities of the system.")
    st.markdown("---")
    st.subheader("Quick Glance")

    fetch_borrowers()
    fetch_loans()

    total_active_loans = len([loan for loan in st.session_state.loans if get_loan_status(loan) == "Active"])
    total_due_soon = len([loan for loan in st.session_state.loans if get_loan_status(loan) == "Due Soon"])
    total_overdue_loans = len([loan for loan in st.session_state.loans if get_loan_status(loan) == "Overdue"])
    total_borrowers = len(st.session_state.borrowers)

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Total Borrowers", total_borrowers)
    with col2:
        st.metric("Active Loans", total_active_loans)
    with col3:
        st.metric("Loans Due Soon", total_due_soon)
    with col4:
        st.metric("Overdue Loans", total_overdue_loans)

    st.subheader("Recent Loan Activity")
    if st.session_state.loans:
        recent_loans_display = []
        sorted_loans = sorted(st.session_state.loans, key=lambda x: x['loan_date'], reverse=True)
        for loan in sorted_loans[:5]:
            borrower_name = st.session_state.borrowers.get(loan['borrower_id'], {}).get('name', 'N/A')
            recent_loans_display.append({
                "Loan ID": loan['loan_id'][:8] + "...",
                "Borrower": borrower_name,
                "Original Amount": f"${loan['amount']:,.2f}",
                "Loan Date": loan['loan_date'],
                "Status": get_loan_status(loan),
                "Current Outstanding": f"${loan['current_outstanding_balance']:,.2f}"
            })
        st.dataframe(recent_loans_display, use_container_width=True, hide_index=True)
    else:
        st.info("No loans created yet. Start by registering a borrower and creating a loan!")

elif page == "Loan Management":
    loan_management_main()
elif page == "Record Payment":
    record_payment()
elif page == "View Loans":
    view_loans()
elif page == "View Borrowers":
    view_borrowers()
elif page == "Edit":
    edit_main()
elif page == "Delete Loan":
    delete_loan()
elif page == "Notifications":
    notifications()