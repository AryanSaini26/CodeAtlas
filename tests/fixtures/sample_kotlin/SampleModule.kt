import kotlin.collections.List
import java.io.File

const val MAX_SIZE = 100
val APP_NAME = "CodeAtlas"

// Defines greeting behavior
interface Greeter {
    fun greet(): String
}

// Base entity
open class Entity(val id: Long)

/**
 * Manages user operations
 */
class UserService : Entity(0), Greeter {
    // Creates a new user
    fun createUser(name: String): String {
        validate(name)
        return format(name)
    }

    override fun greet(): String {
        return "Hello"
    }

    companion object {
        fun create(): UserService = UserService()
    }
}

// Singleton configuration
object Config {
    fun load(): Config {
        return readConfig()
    }
}

fun processAll(items: List<String>) {
    items.forEach { doWork(it) }
}
