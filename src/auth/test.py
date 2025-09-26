import bcrypt
import base64

# Your provided hash
provided_hash = "$2b$12$aZ3aknrtKpO3mXOcGHTn2ugZSNABQzx86FzwgUn0UYqaE9GVVP1am"

print("=== BCRYPT HASH ANALYSIS ===")
print(f"Provided hash: {provided_hash}")
print()

# Parse the bcrypt hash components
parts = provided_hash.split('$')
algorithm = parts[1]  # "2b"
cost = parts[2]       # "12"
salt_and_hash = parts[3]  # "aZ3aknrtKpO3mXOcGHTn2ugZSNABQzx86FzwgUn0UYqaE9GVVP1am"

# In bcrypt, the salt is the first 22 characters of the salt_and_hash part
salt_b64 = salt_and_hash[:22]
hash_b64 = salt_and_hash[22:]

print("=== HASH COMPONENTS ===")
print(f"Algorithm: {algorithm}")
print(f"Cost factor: {cost}")
print(f"Salt (base64): {salt_b64}")
print(f"Hash (base64): {hash_b64}")
print()

# Reconstruct the salt portion for bcrypt
salt_portion = f"${algorithm}${cost}${salt_b64}"
print(f"Salt portion for bcrypt: {salt_portion}")
print()

# Test with "pass1234"
test_password = "pass1234"
print("=== TESTING WITH 'pass1234' ===")

# Hash "pass1234" using the extracted salt
new_hash = bcrypt.hashpw(test_password.encode('utf-8'), salt_portion.encode('utf-8'))
new_hash_str = new_hash.decode('utf-8')

print(f"Original hash: {provided_hash}")
print(f"New hash:      {new_hash_str}")
print()

# Compare the hashes
if provided_hash == new_hash_str:
    print("✅ MATCH! The password 'pass1234' produces the same hash.")
    print("This means 'pass1234' is likely the original password.")
else:
    print("❌ NO MATCH. The password 'pass1234' does not produce the same hash.")
    print("This means 'pass1234' is NOT the original password.")

print()

# Verify using bcrypt's built-in check function
verification_result = bcrypt.checkpw(test_password.encode('utf-8'), provided_hash.encode('utf-8'))
print(f"bcrypt.checkpw() verification: {'✅ VALID' if verification_result else '❌ INVALID'}")

print()
print("=== ADDITIONAL INFO ===")
print("Bcrypt hash format: $algorithm$cost$salt+hash")
print("- Algorithm: 2b (bcrypt variant)")
print("- Cost: 12 (2^12 = 4096 iterations)")
print("- Salt: First 22 chars of the base64 portion")
print("- Hash: Remaining chars of the base64 portion")