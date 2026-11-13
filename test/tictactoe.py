import random


def guess_number():
    number = random.randint(1, 100)
    attempts = 0
    print("Welcome to the Guessing Game!")
    print("I'm thinking of a number between 1 and 100.")
    print("Can you guess it?")

    while True:
        try:
            guess = int(input("Enter your guess: "))
            attempts += 1

            if guess < number:
                print("Too low! Try again.")
            elif guess > number:
                print("Too high! Try again.")
            else:
                print(f"Congratulations! You guessed the number in {attempts} attempts.")
                break
        except ValueError:
            print("Please enter a valid integer.")

if __name__ == "__main__":
    guess_number()