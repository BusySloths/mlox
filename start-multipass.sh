#!/bin/bash
# This script launches a user-specified number of multipass instances.

# Prompt the user for the number of instances to create.
read -p "Enter the number of instances to create: " num_instances

# Validate that the input is a positive integer.
if ! [[ "$num_instances" =~ ^[1-9][0-9]*$ ]]; then
    echo "Error: Please enter a valid positive number."
    exit 1
fi

echo "Preparing to launch $num_instances instance(s)..."

# Loop from 1 to the specified number.
for i in $(seq 1 "$num_instances"); do
    instance_name="instance$i"
    echo "--------------------------------------------------"
    echo "Launching instance #$i: $instance_name"
    multipass launch --cpus 2 --disk 10G --memory 4G --name "$instance_name" --cloud-init cloud-init.yaml
done

echo "--------------------------------------------------"
echo "Script finished. All requested instances have been launched."