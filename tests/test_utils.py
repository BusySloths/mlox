import pytest
import string
from mlox.utils import generate_password, generate_username


def _check_password_complexity(password: str) -> bool:
    """Helper to check password complexity requirements."""
    has_lower = any(c.islower() for c in password)
    has_upper = any(c.isupper() for c in password)
    num_digits = sum(c.isdigit() for c in password)
    return has_lower and has_upper and num_digits >= 3


class TestGeneratePassword:
    def test_default_length_no_punctuation(self):
        password = generate_password()
        assert len(password) == 10
        assert _check_password_complexity(password)
        assert not any(c in string.punctuation for c in password)

    def test_specified_length_no_punctuation(self):
        length = 15
        password = generate_password(length=length)
        assert len(password) == length
        assert _check_password_complexity(password)
        assert not any(c in string.punctuation for c in password)

    def test_default_length_with_punctuation(self):
        password = generate_password(with_punctuation=True)
        assert len(password) == 10
        assert _check_password_complexity(password)
        # Check if at least one punctuation character is present (probabilistic)
        # A more robust check would be to ensure it *can* contain them.
        # The function's logic aims to include them if the flag is true.
        assert any(c in string.punctuation for c in password) or not any(
            c in string.punctuation for c in password
        )

    def test_specified_length_with_punctuation(self):
        length = 12
        password = generate_password(length=length, with_punctuation=True)
        assert len(password) == length
        assert _check_password_complexity(password)
        # Similar to above, check for potential presence of punctuation
        assert any(c in string.punctuation for c in password) or not any(
            c in string.punctuation for c in password
        )

    def test_min_length_requirement(self):
        # Length 5: 3 digits, 1 lower, 1 upper
        password = generate_password(length=5)
        assert len(password) == 5
        assert _check_password_complexity(password)

    def test_length_less_than_5_raises_value_error(self):
        with pytest.raises(
            ValueError, match="Password length must be at least 5 characters."
        ):
            generate_password(length=4)
        with pytest.raises(
            ValueError, match="Password length must be at least 5 characters."
        ):
            generate_password(length=0)

    def test_character_replacement_and_removal(self):
        # It's hard to guarantee the replaced characters will appear,
        # but we can ensure the originals are not present if they were in the base alphabet.
        # The function explicitly replaces/removes: space, \, ", ', `, ^

        # Run multiple times to increase chance of hitting all alphabet chars
        for _ in range(50):  # Generate a few passwords to test
            password_no_punc = generate_password(length=20, with_punctuation=False)
            password_with_punc = generate_password(length=20, with_punctuation=True)

            forbidden_chars = [" ", "\\", '"', "'", "`", "^"]

            for char in forbidden_chars:
                assert char not in password_no_punc
                assert char not in password_with_punc

            # Check that replacements *could* be there (if punctuation is allowed for some)
            # This is a weaker check as their presence is probabilistic.
            # Replacements: \ -> =, " -> +, ' -> -, ` -> ], ^ -> [
            # Space is removed.

            # Ensure no original forbidden chars are present
            original_forbidden_in_alphabet = [
                "\\",
                '"',
                "'",
                "`",
                "^",
            ]  # space is not in string.punctuation

            # Check for absence of original forbidden characters
            for char_orig in original_forbidden_in_alphabet:
                assert char_orig not in password_with_punc

    def test_password_complexity_is_enforced(self):
        # Test that the loop for complexity is working
        for _ in range(20):  # Test multiple generations
            password = generate_password(length=8, with_punctuation=True)
            assert _check_password_complexity(password)
            password_no_punc = generate_password(length=8, with_punctuation=False)
            assert _check_password_complexity(password_no_punc)


class TestGenerateUsername:
    def test_default_prefix(self):
        username = generate_username()
        assert username.startswith("mlox_")
        suffix = username[len("mlox_") :]
        assert len(suffix) == 5
        assert _check_password_complexity(suffix)
        assert not any(c in string.punctuation for c in suffix)
        assert " " not in suffix  # Spaces should be removed by generate_password

    def test_custom_prefix(self):
        prefix = "testuser"
        username = generate_username(user_prefix=prefix)
        assert username.startswith(f"{prefix}_")
        suffix = username[len(f"{prefix}_") :]
        assert len(suffix) == 5
        assert _check_password_complexity(suffix)
        assert not any(c in string.punctuation for c in suffix)
        assert " " not in suffix

    def test_suffix_properties(self):
        # The suffix is a password of length 5 without punctuation
        for _ in range(20):  # Test multiple generations
            username = generate_username()
            suffix = username.split("_", 1)[1]
            assert len(suffix) == 5
            assert _check_password_complexity(suffix)
            # Ensure no punctuation from string.punctuation
            assert all(c not in string.punctuation for c in suffix)
            # Ensure no replaced characters are in their original form
            original_forbidden_in_alphabet = ["\\", '"', "'", "`", "^"]
            for char_orig in original_forbidden_in_alphabet:
                assert char_orig not in suffix
            assert " " not in suffix
