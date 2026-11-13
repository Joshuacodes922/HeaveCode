def binary_search(arr, target):
    """
    Perform binary search on a sorted array to find a target value.
    
    Parameters:
    arr (list): A sorted list of elements to search through.
    target: The value to search for.
    
    Returns:
    int: The index of the target if found, -1 if not found.
    """
    if not arr:
        return -1  # Return -1 if the array is empty

    left, right = 0, len(arr) - 1

    while left <= right:
        mid = (left + right) // 2

        if arr[mid] == target:
            return mid  # Target found at index `mid`
        elif arr[mid] < target:
            left = mid + 1  # Search the right half
        else:
            right = mid - 1  # Search the left half

    return -1  # Target not found

# Example usage
if __name__ == "__main__":
    # Test with a sorted list
    sorted_list = [1, 3, 5, 7, 9, 11, 13, 15]

    # Get user input
    target = int(input("Enter a number to search (from 1-15): "))

    # Perform binary search
    result = binary_search(sorted_list, target)

    # Display result
    if result != -1:
        print(f"Target found at index {result}")
    else:
        print("Target not found in the list.")