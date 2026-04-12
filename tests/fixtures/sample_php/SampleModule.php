<?php

namespace App\Services;

use App\Models\User;
use App\Contracts\Greeting;

const MAX_RETRIES = 3;

// Defines greeting behavior
interface Greeter
{
    public function greet(): string;
}

/**
 * Manages user operations
 */
class UserService extends BaseService implements Greeter
{
    // Creates a new user
    public function createUser(string $name): User
    {
        $user = new User($name);
        validate($user);
        return $user;
    }

    public static function create(): self
    {
        return new self();
    }

    public function greet(): string
    {
        return format('Hello');
    }
}

// An admin with extra privileges
class AdminService extends UserService
{
    public function promote(User $user): void
    {
        update($user);
    }
}

// Top-level utility function
function processAll(array $items): void
{
    foreach ($items as $item) {
        transform($item);
    }
}
