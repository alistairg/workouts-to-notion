# GitHub Copilot Repository Instructions

> **THE MOST IMPORTANT PART: KEEP THINGS SIMPLE!**  
> This is a private passion project, not a complex enterprise system. DO NOT OVERCOMPLICATE THINGS.  
> **FOCUS ON ONLY PERFORMING SMALL AND INCREMENTAL CHANGES UNLESS EXPLICITLY ASKED OTHERWISE.**

**Purpose**: These instructions guide GitHub Copilot's code suggestions and responses for this repository.  
**Scope**: Applies to all files (`**/*`).

## Core Guidelines

When generating code or providing suggestions, Copilot should:

- Prioritize security and maintainability over brevity
- Include appropriate error handling and logging
- Include inline documentation for complex logic
- Only perform the steps you are asked to perform. If there are additional steps that are required, please ask the user to perform them
- Fix any compiler warnings and errors before going to the next step

## 1. Development Principles

### 1.1 Code Quality Standards

- **Clarity over cleverness**: Write code that is easy to read and maintain
- **Contextual comments**: Explain the rationale and business logic, not just the implementation
- **Robust error handling**: Provide clear, actionable messages and recovery paths
- **Architecture notes**: Document design decisions, trade-offs, and high-level diagrams where useful
- **Performance awareness**: Note algorithmic complexity and potential optimizations
- **Tests**: Tests are not required unless explicitly requested

### 1.2 Security Requirements

- **Input validation**: Sanitize and validate all external inputs
- **Least privilege**: Restrict permissions to the minimum required
- **Secrets management**: Store sensitive data in secure vaults or environment variables
- **Encryption**: Protect data at rest and in transit
- **Audit logging**: Record security-relevant events for traceability

## 2. Documentation Standards

- README files are located in the `docs/` folder and should be updated accordingly when new features are added or existing features are modified
- Explanations should be kept concise and to the point
- Keep architecture diagrams and deployment guides up to date
- Version APIs and infrastructure changes using semantic versioning

## 3. Quality Assurance

### Code Review Checklist

- **Readability**: Is the code easy to follow?
- **Security**: Are inputs validated and secrets secured?
- **Performance**: Are any obvious bottlenecks addressed?
- **Documentation**: Are public interfaces and modules documented?
- **Compliance**: Does it follow the guidelines above?

### Anti-Patterns to Avoid

Copilot should **NOT** generate:

- Code with hardcoded credentials or connection strings
- Synchronous code when async alternatives exist
- Direct database queries without parameterization
- Console.log or print statements in production code
- Generic error messages like "An error occurred"
- Code that bypasses security validations
- Comments that simply restate the code

## 4. hevy_webhook Specific Guidelines
When working on hevy_webhook, follow these guidelines:

1. Always use context7 to get up-to-date information on Hevy and Notion API documentation.
2. See https://api.hevyapp.com/docs for Hevy API documentation and examples.
3. Use the Notion tool to get Information about Database structures. The following Databases are in Use:
    - "Workouts" Database - Stores workout entries, Notion Database ID: 2a4c2516b45880cbaec1f51bdf647061
    - "Exercises" Database - Stores exercise details, Notion Database ID: 2a4c2516b4588044ada1c6c7b072c192
    - "Exercise Performances" Database - Stores each performance of an Exercise, Notion Database ID: 2a4c2516b45880fb9f9ed477db7eefd9