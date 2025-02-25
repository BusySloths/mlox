import os
import streamlit as st

from Crypto.PublicKey import RSA

from mlox.configs import Ubuntu24Server, Infrastructure


def add_server_to_infrastructure():
    # st.set_page_config(page_title="VPS Install Page", page_icon="🌍")
    # st.markdown("# VPS Install")

    c1, c2 = st.columns([80, 20])
    ip = c1.text_input("IP Address", "194.163.165.102")
    port = str(c2.number_input("Port", 1, 9999, 22, step=1))

    c1, c2 = st.columns(2)
    root = c1.text_input("Root", "root")
    root_pw = c2.text_input("Password", os.environ.get("TEST_SERVER_PW", ""))

    public_key = st.text_area(
        "Local machine public key (added to the VPS server for SSH authentication)",
        "",
        help="Public key is added to the VPS server in order to authenticate and login.",
    )
    try:
        _ = RSA.import_key(public_key)
    except Exception as e:
        st.error(f"An error occurred while importing the public key: {e}")

    passphrase = st.text_input(
        "Local machine private key passphrase for SSH authentication",
        "",
        help="Passphrase of the local private key in order to establish a SSH connection with the VPS once the public key has been added.",
    )

    my_server = Ubuntu24Server(ip, root, root_pw, public_key, passphrase)
    # if st.button("Setup"):
    #     my_server.setup()
    #     with my_server.get_server_connection() as conn:
    #         st.write(f"{sys_disk_free(conn)} DISK FREE")
    #     st.write(my_server.get_server_connection().credentials)

    # if st.button("Upgrade"):
    #     my_server.update()

    # if st.button("Install Packages"):
    #     my_server.install_packages()

    if st.button("Add to server list"):
        Infrastructure.get_instance().add_server(my_server)
        print("ADD Server")


# run()
