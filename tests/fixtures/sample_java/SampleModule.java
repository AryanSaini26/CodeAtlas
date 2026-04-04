package com.example.app;

import java.util.List;
import java.util.Optional;

/**
 * Represents a user in the system.
 */
public class User extends BaseEntity implements Serializable {
    private String name;
    private int age;
    public static final int MAX_AGE = 150;

    public User(String name, int age) {
        this.name = name;
        this.age = age;
    }

    /**
     * Returns the user's name.
     */
    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }

    public static User create(String name, int age) {
        return new User(name, age);
    }
}

public interface UserService {
    Optional<User> findById(long id);
    List<User> findAll();
}

public enum Role {
    ADMIN,
    USER,
    GUEST;
}

public record Point(int x, int y) {}

public abstract class BaseEntity {
    protected long id;

    public abstract long getId();
}
