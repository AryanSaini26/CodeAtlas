/**
 * Sample TypeScript module for testing the CodeAtlas TypeScript parser.
 */

import { EventEmitter } from "events";
import * as path from "path";
import defaultExport from "./other-module";

export const API_VERSION = "1.0.0";
export let instanceCount = 0;

/** Represents a user in the system. */
export interface User {
    id: number;
    name: string;
    email: string;
}

/** Status of a task. */
export enum TaskStatus {
    Pending = "pending",
    Running = "running",
    Done = "done",
}

/** Generic result type. */
export type Result<T> = {
    data: T;
    error: string | null;
};

/** A standalone exported function. */
export function greet(name: string): string {
    return `Hello, ${name}`;
}

/** An arrow function assigned to a const. */
export const formatUser = (user: User): string => {
    return `${user.name} <${user.email}>`;
};

/** A generic utility function. */
export function identity<T>(value: T): T {
    return value;
}

/** Base class for services. */
export class BaseService {
    protected name: string;

    constructor(name: string) {
        this.name = name;
    }

    /** Get the service name. */
    getName(): string {
        return this.name;
    }
}

/** User service extending BaseService and implementing an interface. */
export interface Describable {
    describe(): string;
}

export class UserService extends BaseService implements Describable {
    private users: User[] = [];

    constructor() {
        super("UserService");
    }

    /** Add a user to the service. */
    addUser(user: User): void {
        instanceCount++;
        this.users.push(user);
    }

    /** Find a user by ID. */
    findById(id: number): User | undefined {
        return this.users.find((u) => u.id === id);
    }

    describe(): string {
        return `${this.getName()} with ${this.users.length} users`;
    }
}

/** A type alias for a callback. */
export type UserCallback = (user: User) => void;

export namespace Utils {
    export function slugify(input: string): string {
        return input.toLowerCase().replace(/\s+/g, "-");
    }

    export const VERSION = "0.1.0";
}
