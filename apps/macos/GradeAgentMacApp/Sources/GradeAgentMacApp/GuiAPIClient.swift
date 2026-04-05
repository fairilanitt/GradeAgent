import Foundation

actor GuiAPIClient {
    private let baseURL: URL
    private let decoder: JSONDecoder
    private let encoder: JSONEncoder

    init(baseURL: URL? = nil) {
        self.baseURL = Self.resolvedBaseURL(override: baseURL)

        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        decoder.dateDecodingStrategy = .iso8601
        self.decoder = decoder

        let encoder = JSONEncoder()
        encoder.keyEncodingStrategy = .convertToSnakeCase
        encoder.dateEncodingStrategy = .iso8601
        self.encoder = encoder
    }

    static func shutdownSynchronously(baseURL: URL? = nil, timeout: TimeInterval = 2.0) {
        let requestURL = resolvedBaseURL(override: baseURL).appending(path: "gui/shutdown")
        var request = URLRequest(url: requestURL)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try? JSONEncoder().encode(EmptyPayload())
        request.timeoutInterval = timeout

        let configuration = URLSessionConfiguration.ephemeral
        configuration.timeoutIntervalForRequest = timeout
        configuration.timeoutIntervalForResource = timeout

        let session = URLSession(configuration: configuration)
        let semaphore = DispatchSemaphore(value: 0)
        let task = session.dataTask(with: request) { _, _, _ in
            semaphore.signal()
        }

        task.resume()
        let waitResult = semaphore.wait(timeout: .now() + timeout)
        if waitResult == .timedOut {
            task.cancel()
        }
        session.invalidateAndCancel()
    }

    func state() async throws -> GuiStateResponse {
        try await get("gui/state")
    }

    func startBrowser() async throws -> GuiBrowserStartResponse {
        try await post("gui/browser/start", body: EmptyPayload())
    }

    func stopBrowser() async throws -> GuiStateResponse {
        try await post("gui/browser/stop", body: EmptyPayload())
    }

    func overview() async throws -> GuiOverviewResponse {
        try await get("gui/overview")
    }

    func prompts() async throws -> [GuiPromptTemplate] {
        try await get("gui/prompts")
    }

    func newPrompt() async throws -> GuiPromptTemplate {
        try await post("gui/prompts/new", body: EmptyPayload())
    }

    func savePrompt(_ request: GuiPromptSaveRequest) async throws -> GuiPromptTemplate {
        try await post("gui/prompts/save", body: request)
    }

    func gradeExercise(_ request: GuiGradeExerciseRequest) async throws -> GuiGradeExerciseResponse {
        try await post("gui/exercises/grade", body: request)
    }

    func statistics() async throws -> GuiStatisticsResponse {
        try await get("gui/statistics")
    }

    func shutdown() async {
        do {
            try await postNoContent("gui/shutdown", body: EmptyPayload())
        } catch {
            return
        }
    }

    private func get<Response: Decodable>(_ path: String) async throws -> Response {
        var request = URLRequest(url: endpoint(path))
        request.httpMethod = "GET"
        return try await send(request)
    }

    private func post<RequestBody: Encodable, Response: Decodable>(_ path: String, body: RequestBody) async throws -> Response {
        var request = URLRequest(url: endpoint(path))
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try encoder.encode(body)
        return try await send(request)
    }

    private func postNoContent<RequestBody: Encodable>(_ path: String, body: RequestBody) async throws {
        var request = URLRequest(url: endpoint(path))
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try encoder.encode(body)
        _ = try await sendRaw(request)
    }

    private func endpoint(_ path: String) -> URL {
        baseURL.appending(path: path)
    }

    private static func resolvedBaseURL(override: URL? = nil) -> URL {
        if let override {
            return override
        }
        if let raw = ProcessInfo.processInfo.environment["GRADEAGENT_GUI_API_BASE_URL"],
           let parsed = URL(string: raw) {
            return parsed
        }
        return URL(string: "http://127.0.0.1:8765/api")!
    }

    private func send<Response: Decodable>(_ request: URLRequest) async throws -> Response {
        let (data, _) = try await sendRaw(request)
        if data.isEmpty {
            throw GuiAPIClientError.invalidResponse("Tyhjä vastaus palvelimelta.")
        }
        do {
            return try decoder.decode(Response.self, from: data)
        } catch {
            throw GuiAPIClientError.invalidResponse("Palvelimen vastausta ei voitu tulkita.")
        }
    }

    private func sendRaw(_ request: URLRequest) async throws -> (Data, HTTPURLResponse) {
        let (data, response) = try await URLSession.shared.data(for: request)
        guard let httpResponse = response as? HTTPURLResponse else {
            throw GuiAPIClientError.invalidResponse("Palvelin ei palauttanut HTTP-vastausta.")
        }
        guard (200 ... 299).contains(httpResponse.statusCode) else {
            if let serverError = try? decoder.decode(ApiErrorResponse.self, from: data) {
                throw GuiAPIClientError.server(serverError.detail)
            }
            throw GuiAPIClientError.server("Palvelin palautti virheen \(httpResponse.statusCode).")
        }
        return (data, httpResponse)
    }
}

private struct EmptyPayload: Encodable {}

enum GuiAPIClientError: LocalizedError {
    case server(String)
    case invalidResponse(String)

    var errorDescription: String? {
        switch self {
        case .server(let message), .invalidResponse(let message):
            return message
        }
    }
}
