# Patchly RCA Agent

An AI-powered Root Cause Analysis (RCA) agent for production incident investigation. Analyzes logs, alerts, and incident data using LLMs to provide automated root cause analysis.

## Features

- **Multiple Input Sources**: Analyze text alerts, log files, or JSON payloads
- **Multi-LLM Support**: Works with Ollama, OpenAI, Azure OpenAI, Anthropic, and Google Gemini
- **FastAPI Backend**: RESTful API for integration with existing systems
- **Streamlit UI**: Interactive web interface for incident analysis
- **Docker Support**: Easy deployment with Docker Compose
- **MCP Integration**: Optional Model Context Protocol server support

## Quick Start

### Prerequisites

- Python 3.12+
- pip or uv package manager

### Installation

1. Clone the repository:
```bash
git clone <repository-url>
cd patchly-rca-agentLatest
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Configure environment:
```bash
cp .env.example .env
# Edit .env with your LLM provider credentials
```

### Configuration

Edit `.env` to configure your LLM provider:

```env
LLM_PROVIDER=gemini          # ollama | openai | azure_openai | anthropic | gemini
LLM_MODEL=gemini-2.5-flash   # Model name
LLM_TEMPERATURE=0.0
LLM_MAX_TOKENS=4096

# Add your API key for the chosen provider
GEMINI_API_KEY=your_key_here
```

## Usage

### CLI Mode

**Interactive prompt:**
```bash
python main.py
```

**Analyze a log file:**
```bash
python main.py --log /var/log/app.log
```

**Analyze text alert:**
```bash
python main.py --text "payment service down"
```

**Read from file:**
```bash
python main.py --file alert.txt
```

### Server Mode

**Start API server (port 8000):**
```bash
python main.py api
```

**Start Streamlit UI (port 8501):**
```bash
python main.py ui
```

**Start both:**
```bash
python main.py both
```

### Docker Deployment

```bash
docker-compose up
```

Access:
- API: http://localhost:8000
- UI: http://localhost:8501

## Project Structure

```
patchly-rca-agentLatest/
├── src/patchly_rca/
│   ├── agent/          # Core RCA agent logic
│   ├── api/            # FastAPI endpoints
│   ├── config/         # Configuration management
│   ├── ingestion/      # Data ingestion modules
│   ├── mcp_loader/     # MCP server integration
│   └── tools/          # Agent tools
├── ui/                 # Streamlit interface
├── tests/              # Unit tests
├── rca_reports/        # Generated RCA reports
├── main.py             # Entry point
├── requirements.txt    # Dependencies
└── docker-compose.yml  # Docker configuration
```

## LLM Provider Setup

### Ollama (Local)
```env
LLM_PROVIDER=ollama
OLLAMA_BASE_URL=http://localhost:11434
LLM_MODEL=llama3
```

### OpenAI
```env
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-...
LLM_MODEL=gpt-4
```

### Google Gemini
```env
LLM_PROVIDER=gemini
GEMINI_API_KEY=AIza...
LLM_MODEL=gemini-2.5-flash
```

### Azure OpenAI
```env
LLM_PROVIDER=azure_openai
AZURE_OPENAI_ENDPOINT=https://...
AZURE_OPENAI_KEY=...
AZURE_OPENAI_DEPLOYMENT=gpt-4o
```

### Anthropic
```env
LLM_PROVIDER=anthropic
ANTHROPIC_API_KEY=sk-ant-...
LLM_MODEL=claude-3-opus-20240229
```

## Integration with Java Spring Boot Applications

### Integration Checklist

1. Enable in `src/main/resources/application.properties`
2. Auto-config loads via `RcaAutoConfiguration` (conditional on `rca.agent.enabled`)
3. Client: `RcaAgentClient` calls `/analyze` and `/health`
4. AOP: `RcaAspect` intercepts and calls `rcaClient.analyseAsync(...)`
5. Global handler: `GlobelExceptionHandler` calls `rcaClient.analyseAsync(...)`
6. Per-method opt-in: annotate method with `@TriggerRca`

### Step 1: Configure application.properties

Add the following configuration to `src/main/resources/application.properties`:

```properties
# RCA agent
rca.agent.enabled=true
rca.agent.base-url=https://patchly-rca-agent.onrender.com
rca.agent.timeout-seconds=120
rca.agent.max-retries=2

# AOP aspect (optional)
rca.aspect.enabled=true

# Optional notifications
rca.notification.slack-webhook=
rca.notification.webhook-url=
```

### Step 2: Import Auto-Configuration

Ensure auto-config is imported in your main application class:

```java
// src/main/java/com/vinay/InsuranceManagementSystemApplication.java
import org.springframework.context.annotation.Import;
import com.vinay.config.RcaAutoConfiguration;

@SpringBootApplication
@Import(RcaAutoConfiguration.class)
public class InsuranceManagementSystemApplication {
    public static void main(String[] args) {
        SpringApplication.run(InsuranceManagementSystemApplication.class, args);
    }
}
```

### Step 3: Create RcaAutoConfiguration

```java
// src/main/java/com/vinay/config/RcaAutoConfiguration.java
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;
import org.springframework.scheduling.annotation.EnableAsync;

@Configuration
@ConditionalOnProperty(name = "rca.agent.enabled", havingValue = "true", matchIfMissing = true)
@EnableAspectJAutoProxy
@EnableAsync
public class RcaAutoConfiguration {
    
    @Bean
    @ConditionalOnProperty(name = "rca.aspect.enabled", havingValue = "true", matchIfMissing = true)
    public RcaAspect rcaAspect() {
        return new RcaAspect();
    }
    
    // Logs agent health at startup
    @PostConstruct
    public void checkAgentHealth() {
        log.info("RCA Agent auto-configuration loaded");
    }
}
```

### Step 4: Implement RcaAgentClient

```java
// src/main/java/com/vinay/clientImpl/RcaAgentClient.java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestTemplate;
import java.util.Optional;
import java.util.concurrent.CompletableFuture;

@Component
public class RcaAgentClient {
    
    @Value("${rca.agent.base-url}")
    private String baseUrl;
    
    private final RestTemplate restTemplate = new RestTemplate();
    
    // Async entry used by handlers
    public CompletableFuture<Optional<RcaResponse>> analyseAsync(String input) {
        return CompletableFuture.supplyAsync(() -> analyse(input));
    }
    
    // Optional sync version (avoid on request thread)
    public Optional<RcaResponse> analyse(String input) {
        try {
            Map<String, String> request = Map.of("input", input);
            RcaResponse response = restTemplate.postForObject(
                baseUrl + "/analyze", 
                request, 
                RcaResponse.class
            );
            return Optional.ofNullable(response);
        } catch (Exception e) {
            log.error("RCA analysis failed", e);
            return Optional.empty();
        }
    }
    
    // Health check used at startup
    public boolean isAgentHealthy() {
        try {
            restTemplate.getForObject(baseUrl + "/health", String.class);
            return true;
        } catch (Exception e) {
            return false;
        }
    }
}
```

### Step 5: Create AOP Aspect for Service Layer

```java
// src/main/java/com/vinay/aspect/RcaAspect.java
import org.aspectj.lang.ProceedingJoinPoint;
import org.aspectj.lang.annotation.Around;
import org.aspectj.lang.annotation.Aspect;
import org.springframework.beans.factory.annotation.Autowired;

@Aspect
public class RcaAspect {
    
    @Autowired
    private RcaAgentClient rcaClient;
    
    @Around("within(@org.springframework.stereotype.Service *)")
    public Object aroundService(ProceedingJoinPoint pjp) throws Throwable {
        try {
            return pjp.proceed();
        } catch (Throwable ex) {
            // Build payload (service, method, args, etc.)
            String payload = IncidentPayload.from((Exception) ex)
                .service(pjp.getTarget().getClass().getSimpleName())
                .method(pjp.getSignature().getName())
                .build();
            
            // Fire-and-forget
            rcaClient.analyseAsync(payload)
                .thenAccept(opt -> opt.ifPresent(r -> 
                    log.info("RCA report generated: {}", r)
                ));
            
            throw ex;
        }
    }
}
```

### Step 6: Create Global Exception Handler

```java
// src/main/java/com/vinay/exception/GlobelExceptionHandler.java
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ControllerAdvice;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.context.request.WebRequest;

@ControllerAdvice
public class GlobelExceptionHandler {
    
    @Autowired
    private RcaAgentClient rcaClient;
    
    @Autowired
    private RcaNotificationService notificationService;
    
    @ExceptionHandler(Exception.class)
    public ResponseEntity<Map<String, Object>> handleAll(Exception ex, WebRequest request) {
        String requestPath = request.getDescription(false).replace("uri=", "");
        
        // Build payload
        String payload = IncidentPayload.from(ex)
            .service(serviceName)
            .environment(environment)
            .endpoint(requestPath)
            .severity(classifySeverity(ex))
            .build();
        
        // Async RCA analysis
        rcaClient.analyseAsync(payload)
            .thenAccept(optResponse -> optResponse.ifPresentOrElse(
                response -> notificationService.send(ex, requestPath, response),
                () -> log.warn("No RCA report generated")
            ))
            .exceptionally(t -> {
                log.error("RCA analysis failed", t);
                return null;
            });
        
        // Return sanitized 500 response
        Map<String, Object> errorResponse = new HashMap<>();
        errorResponse.put("status", 500);
        errorResponse.put("message", "Internal Server Error");
        errorResponse.put("path", requestPath);
        
        return ResponseEntity.status(500).body(errorResponse);
    }
    
    private String classifySeverity(Exception ex) {
        // Classify based on exception type
        if (ex instanceof NullPointerException) return "HIGH";
        if (ex instanceof IllegalArgumentException) return "MEDIUM";
        return "LOW";
    }
}
```

### Maven Dependencies

```xml
<dependencies>
    <!-- Spring Boot Starter Web -->
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
    
    <!-- Spring Boot Starter AOP -->
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-aop</artifactId>
    </dependency>
    
    <!-- Jackson for JSON -->
    <dependency>
        <groupId>com.fasterxml.jackson.core</groupId>
        <artifactId>jackson-databind</artifactId>
        <version>2.15.2</version>
    </dependency>
</dependencies>
```

### Gradle Dependencies

```gradle
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-aop'
    implementation 'com.fasterxml.jackson.core:jackson-databind:2.15.2'
}
```

## Development

### Running Tests
```bash
pytest tests/
```

### Project Setup
```bash
pip install -e .
```

## Output

RCA reports are saved to `./rca_reports/` by default. Configure the output directory in `.env`:

```env
RCA_OUTPUT_DIR=./rca_reports
```

## License

[Add your license here]

## Contributing

[Add contribution guidelines here]
