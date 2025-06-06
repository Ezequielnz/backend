#!/usr/bin/env python3
"""
Script to guide the creation of services and subscriptions tables in the database.
Since Supabase doesn't allow direct SQL execution through the client, this script
provides instructions for manually creating the tables.
"""
import sys
import os

# Add the parent directory to the path so we can import from app
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.supabase_client import get_supabase_client

def read_sql_file(file_path):
    """Read SQL file and return its content."""
    with open(file_path, 'r', encoding='utf-8') as file:
        return file.read()

def test_tables_exist():
    """Test if the services and subscriptions tables exist."""
    client = get_supabase_client()
    
    tables_to_check = ['servicios', 'suscripciones']
    existing_tables = []
    missing_tables = []
    
    for table in tables_to_check:
        try:
            result = client.table(table).select('*').limit(1).execute()
            existing_tables.append(table)
            print(f"✅ Table '{table}' exists")
        except Exception as e:
            if 'does not exist' in str(e):
                missing_tables.append(table)
                print(f"❌ Table '{table}' does not exist")
            else:
                print(f"⚠️  Error checking table '{table}': {str(e)}")
    
    return existing_tables, missing_tables

def main():
    """Main function to guide table creation."""
    print("🚀 Checking services and subscriptions tables...")
    print("=" * 60)
    
    # Test database connection
    try:
        client = get_supabase_client()
        client.table('negocios').select('id').limit(1).execute()
        print("✅ Database connection successful")
    except Exception as e:
        print(f"❌ Database connection failed: {str(e)}")
        return
    
    print("\n📋 Checking existing tables...")
    existing_tables, missing_tables = test_tables_exist()
    
    if not missing_tables:
        print("\n🎉 All tables already exist! Services and subscriptions functionality is ready to use.")
        return
    
    print(f"\n📝 Missing tables: {', '.join(missing_tables)}")
    print("\n" + "=" * 60)
    print("📋 MANUAL SETUP REQUIRED")
    print("=" * 60)
    
    # Path to the SQL file
    sql_file_path = os.path.join(os.path.dirname(__file__), 'create_services_subscriptions_tables.sql')
    
    if not os.path.exists(sql_file_path):
        print(f"❌ SQL file not found: {sql_file_path}")
        return
    
    print("\nTo create the missing tables, please follow these steps:")
    print("\n1. 🌐 Open your Supabase dashboard")
    print("2. 📊 Go to the SQL Editor")
    print("3. 📋 Copy and paste the following SQL script:")
    print(f"4. 📁 Or upload the file: {sql_file_path}")
    print("5. ▶️  Execute the SQL script")
    
    print("\n" + "=" * 60)
    print("📄 SQL SCRIPT CONTENT:")
    print("=" * 60)
    
    try:
        sql_content = read_sql_file(sql_file_path)
        print(sql_content)
    except Exception as e:
        print(f"❌ Error reading SQL file: {str(e)}")
        return
    
    print("\n" + "=" * 60)
    print("✅ After executing the SQL script, run this script again to verify the tables were created.")
    print("🚀 Then you can start using the services and subscriptions functionality!")

if __name__ == "__main__":
    main() 