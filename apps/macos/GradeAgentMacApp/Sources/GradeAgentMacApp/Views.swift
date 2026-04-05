import SwiftUI

struct LiquidGlassBackground: View {
    var body: some View {
        ZStack {
            LinearGradient(
                colors: [
                    Color(hex: "#D7DADF"),
                    Color(hex: "#F1F3F5"),
                    Color(hex: "#C9CED4"),
                ],
                startPoint: .topLeading,
                endPoint: .bottomTrailing
            )
            .ignoresSafeArea()

            Circle()
                .fill(Color.white.opacity(0.18))
                .frame(width: 460, height: 460)
                .blur(radius: 80)
                .offset(x: -260, y: -220)

            Circle()
                .fill(Color(hex: "#BCC4CC").opacity(0.28))
                .frame(width: 380, height: 380)
                .blur(radius: 70)
                .offset(x: 300, y: -180)

            Circle()
                .fill(Color(hex: "#E5E8EC").opacity(0.34))
                .frame(width: 460, height: 460)
                .blur(radius: 90)
                .offset(x: 260, y: 260)
        }
    }
}

struct HeroImageOverlayView: View {
    var body: some View {
        ZStack(alignment: .topTrailing) {
            LinearGradient(
                colors: [
                    Color(hex: "#6F7881").opacity(0.96),
                    Color(hex: "#8A939C").opacity(0.90),
                    Color(hex: "#B0B7BE").opacity(0.82),
                ],
                startPoint: .topLeading,
                endPoint: .bottomTrailing
            )

            Image(systemName: "text.book.closed.fill")
                .font(.system(size: 240, weight: .black))
                .foregroundStyle(.white.opacity(0.13))
                .rotationEffect(.degrees(-8))
                .offset(x: 40, y: -10)

            Image(systemName: "character.book.closed")
                .font(.system(size: 180, weight: .light))
                .foregroundStyle(.white.opacity(0.10))
                .offset(x: -180, y: 48)

            Rectangle()
                .fill(
                    LinearGradient(
                        colors: [
                            Color.black.opacity(0.08),
                            Color.clear,
                            Color.clear,
                        ],
                        startPoint: .top,
                        endPoint: .bottom
                    )
                )
        }
        .overlay(
            Rectangle()
                .fill(
                    LinearGradient(
                        colors: [
                            Color.white.opacity(0.06),
                            Color.white.opacity(0.02),
                            Color.clear,
                        ],
                        startPoint: .top,
                        endPoint: .bottom
                    )
                )
                .blur(radius: 12)
        )
    }
}

struct GlassCard<Content: View>: View {
    let padding: CGFloat
    let fillOpacity: Double
    let strokeOpacity: Double
    @ViewBuilder var content: Content

    init(
        padding: CGFloat = 24,
        fillOpacity: Double = 0.08,
        strokeOpacity: Double = 0.24,
        @ViewBuilder content: () -> Content
    ) {
        self.padding = padding
        self.fillOpacity = fillOpacity
        self.strokeOpacity = strokeOpacity
        self.content = content()
    }

    var body: some View {
        ZStack {
            RoundedRectangle(cornerRadius: 34, style: .continuous)
                .fill(Color.white.opacity(fillOpacity))
                .background(.ultraThinMaterial, in: RoundedRectangle(cornerRadius: 34, style: .continuous))

            RoundedRectangle(cornerRadius: 34, style: .continuous)
                .stroke(Color.white.opacity(strokeOpacity), lineWidth: 1.0)

            content
                .padding(padding)
        }
        .shadow(color: .black.opacity(0.14), radius: 24, x: 0, y: 18)
    }
}

struct AdaptiveAxisStack<Content: View>: View {
    let horizontal: Bool
    let alignment: HorizontalAlignment
    let spacing: CGFloat
    @ViewBuilder var content: Content

    init(
        horizontal: Bool,
        alignment: HorizontalAlignment = .leading,
        spacing: CGFloat = 12,
        @ViewBuilder content: () -> Content
    ) {
        self.horizontal = horizontal
        self.alignment = alignment
        self.spacing = spacing
        self.content = content()
    }

    var body: some View {
        Group {
            if horizontal {
                HStack(alignment: .top, spacing: spacing) {
                    content
                }
            } else {
                VStack(alignment: alignment, spacing: spacing) {
                    content
                }
            }
        }
    }
}

struct LiquidGlassButtonStyle: ButtonStyle {
    let tint: Color

    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(.system(size: 13, weight: .bold, design: .rounded))
            .foregroundStyle(.white)
            .padding(.horizontal, 18)
            .padding(.vertical, 12)
            .background(
                ZStack {
                    RoundedRectangle(cornerRadius: 18, style: .continuous)
                        .fill(tint.opacity(configuration.isPressed ? 0.78 : 0.94))

                    RoundedRectangle(cornerRadius: 18, style: .continuous)
                        .fill(
                            LinearGradient(
                                colors: [
                                    Color.white.opacity(configuration.isPressed ? 0.10 : 0.24),
                                    Color.white.opacity(0.02),
                                ],
                                startPoint: .top,
                                endPoint: .bottom
                            )
                        )

                    RoundedRectangle(cornerRadius: 18, style: .continuous)
                        .stroke(Color.white.opacity(0.26), lineWidth: 1)
                }
            )
            .scaleEffect(configuration.isPressed ? 0.985 : 1)
            .shadow(color: tint.opacity(0.26), radius: 14, x: 0, y: 10)
            .animation(.easeOut(duration: 0.12), value: configuration.isPressed)
    }
}

struct CircularActionButtonStyle: ButtonStyle {
    let tint: Color

    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(.system(size: 13, weight: .bold))
            .foregroundStyle(.white)
            .frame(width: 34, height: 34)
            .background(
                Circle()
                    .fill(tint.opacity(configuration.isPressed ? 0.74 : 0.90))
                    .overlay(
                        Circle()
                            .stroke(Color.white.opacity(0.24), lineWidth: 1)
                    )
            )
            .shadow(color: tint.opacity(0.22), radius: 10, x: 0, y: 8)
            .scaleEffect(configuration.isPressed ? 0.96 : 1)
            .animation(.easeOut(duration: 0.12), value: configuration.isPressed)
    }
}

struct SidebarButton: View {
    let title: String
    let systemImage: String
    let selected: Bool
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            HStack(spacing: 12) {
                Image(systemName: systemImage)
                    .font(.system(size: 13, weight: .bold))
                Text(title)
                    .font(.system(size: 13, weight: .bold, design: .rounded))
                Spacer(minLength: 0)
            }
            .foregroundStyle(.white)
            .padding(.horizontal, 12)
            .padding(.vertical, 10)
            .background(
                RoundedRectangle(cornerRadius: 18, style: .continuous)
                    .fill(selected ? Color.white.opacity(0.15) : Color.black.opacity(0.08))
            )
            .overlay(
                RoundedRectangle(cornerRadius: 18, style: .continuous)
                    .stroke(Color.white.opacity(selected ? 0.16 : 0.07), lineWidth: 1)
            )
        }
        .buttonStyle(.plain)
    }
}

struct OverviewMetric: View {
    let label: String
    let value: String

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(label.uppercased())
                .font(.system(size: 10, weight: .bold, design: .rounded))
                .foregroundStyle(.white.opacity(0.62))
            Text(value)
                .font(.system(size: 15, weight: .bold, design: .rounded))
                .foregroundStyle(.white)
        }
        .padding(.vertical, 8)
    }
}

struct HeroDashboardView: View {
    @EnvironmentObject private var store: GuiStore
    let compact: Bool

    var body: some View {
        AdaptiveAxisStack(horizontal: !compact, spacing: compact ? 12 : 18) {
            VStack(alignment: .leading, spacing: 12) {
                Text(store.welcomeTitle)
                    .font(.system(size: compact ? 28 : 32, weight: .bold, design: .rounded))
                    .foregroundStyle(.white)
                    .shadow(color: .black.opacity(0.18), radius: 14, x: 0, y: 8)

                Text("Sanoman kokeiden arviointityötila.")
                    .font(.system(size: 13, weight: .medium, design: .rounded))
                    .foregroundStyle(.white.opacity(0.84))

                ViewThatFits(in: .horizontal) {
                    HStack(spacing: 10) {
                        HeroStatPill(label: "Selaimen tila", value: store.browserReady ? "Auki" : "Ei auki")
                        HeroStatPill(label: "Tehtävät", value: "\(store.detectedExerciseCount)")
                        HeroStatPill(label: "Kriteerit", value: "\(store.prompts.count)")
                        HeroStatPill(label: "Ryhmä", value: store.overview?.groupName ?? "-")
                    }

                    Grid(alignment: .leading, horizontalSpacing: 8, verticalSpacing: 8) {
                        GridRow {
                            HeroStatPill(label: "Selaimen tila", value: store.browserReady ? "Auki" : "Ei auki")
                            HeroStatPill(label: "Tehtävät", value: "\(store.detectedExerciseCount)")
                        }
                        GridRow {
                            HeroStatPill(label: "Kriteerit", value: "\(store.prompts.count)")
                            HeroStatPill(label: "Ryhmä", value: store.overview?.groupName ?? "-")
                        }
                    }
                }
            }
            .frame(maxWidth: compact ? .infinity : 720, alignment: .leading)

            if store.selectedPage == .ohjaus {
                AdaptiveAxisStack(horizontal: !compact, spacing: 10) {
                    HStack(spacing: 10) {
                        Button {
                            Task { await store.startBrowser() }
                        } label: {
                            Image(systemName: "play.fill")
                        }
                        .help("Käynnistä selain")
                        .buttonStyle(CircularActionButtonStyle(tint: Color(hex: "#7E9487")))
                        .disabled(store.isStartingBrowser || store.browserReady)

                        Button {
                            Task { await store.stopBrowser() }
                        } label: {
                            Image(systemName: "stop.fill")
                        }
                        .help("Pysäytä selain")
                        .buttonStyle(CircularActionButtonStyle(tint: Color(hex: "#9A7B7B")))
                        .disabled(!store.browserReady)
                    }

                    Button {
                        Task { await store.stopCurrentGrading() }
                    } label: {
                        Label(
                            store.isStopGradingRequested ? "Pysäytetään arviointi..." : "Pysäytä arviointi",
                            systemImage: store.isStopGradingRequested ? "hourglass" : "pause.circle.fill"
                        )
                    }
                    .buttonStyle(LiquidGlassButtonStyle(tint: Color(hex: "#A08A78")))
                    .disabled(store.gradingColumnKey == nil || store.isStopGradingRequested)
                }
                .frame(maxWidth: compact ? .infinity : nil, alignment: compact ? .leading : .trailing)
                .padding(.top, compact ? 0 : 6)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }
}

struct HeroStatPill: View {
    let label: String
    let value: String

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(label.uppercased())
                .font(.system(size: 10, weight: .bold, design: .rounded))
                .foregroundStyle(.white.opacity(0.66))

            Text(value)
                .font(.system(size: 14, weight: .bold, design: .rounded))
                .foregroundStyle(.white)
                .lineLimit(1)
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 12)
        .frame(minWidth: 118, alignment: .leading)
        .background(Color.white.opacity(0.14))
        .clipShape(RoundedRectangle(cornerRadius: 20, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: 20, style: .continuous)
                .stroke(Color.white.opacity(0.10), lineWidth: 1)
        )
    }
}

struct MiniInfoPill: View {
    let label: String
    let value: String

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(label.uppercased())
                .font(.system(size: 10, weight: .bold, design: .rounded))
                .foregroundStyle(.white.opacity(0.56))

            Text(value)
                .font(.system(size: 12, weight: .semibold, design: .rounded))
                .foregroundStyle(.white.opacity(0.88))
                .lineLimit(2)
                .multilineTextAlignment(.leading)
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 10)
        .background(Color.black.opacity(0.08))
        .clipShape(RoundedRectangle(cornerRadius: 16, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: 16, style: .continuous)
                .stroke(Color.white.opacity(0.07), lineWidth: 1)
        )
    }
}

struct PromptPreviewView: View {
    let prompt: GuiPromptTemplate?

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Kriteerin esikatselu")
                .font(.system(size: 12, weight: .semibold, design: .rounded))
                .foregroundStyle(.white.opacity(0.9))

            ScrollView {
                Text(prompt?.body ?? "Valitse ensin kriteeri Kriteerit-kirjastosta.")
                    .font(.system(size: 12, weight: .medium, design: .rounded))
                    .foregroundStyle(.white.opacity(0.84))
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .textSelection(.enabled)
            }
            .frame(minHeight: 120, maxHeight: 150)
            .padding(14)
            .background(Color.white.opacity(0.08))
            .clipShape(RoundedRectangle(cornerRadius: 20, style: .continuous))
            .overlay(
                RoundedRectangle(cornerRadius: 20, style: .continuous)
                    .stroke(Color.white.opacity(0.14), lineWidth: 1)
            )
        }
    }
}

struct ExerciseInfoLine: View {
    let label: String
    let value: String

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(label.uppercased())
                .font(.system(size: 10, weight: .bold, design: .rounded))
                .foregroundStyle(.white.opacity(0.56))

            Text(value)
                .font(.system(size: 13, weight: .semibold, design: .rounded))
                .foregroundStyle(.white.opacity(0.90))
                .lineLimit(2)
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 10)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Color.black.opacity(0.08))
        .clipShape(RoundedRectangle(cornerRadius: 16, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: 16, style: .continuous)
                .stroke(Color.white.opacity(0.07), lineWidth: 1)
        )
    }
}

struct PromptLibraryBrowserView: View {
    @EnvironmentObject private var store: GuiStore
    @State private var builtInExpanded = true
    @State private var customExpanded = true
    let integrated: Bool

    private let contentInset: CGFloat = 4

    var body: some View {
        LibraryPanelShell(integrated: integrated) {
            VStack(spacing: 0) {
                HStack {
                    VStack(alignment: .leading, spacing: 4) {
                        Text("Kirjasto")
                            .font(.system(size: 18, weight: .bold, design: .rounded))
                            .foregroundStyle(.white)
                        Text("Valitse prompti listasta ja muokkaa sitä alapuolella.")
                            .font(.system(size: 12, weight: .medium, design: .rounded))
                            .foregroundStyle(.white.opacity(0.74))
                    }

                    Spacer(minLength: 0)

                    Button {
                        Task { await store.createPrompt() }
                    } label: {
                        Label("Uusi kriteeri", systemImage: "plus")
                    }
                    .buttonStyle(LiquidGlassButtonStyle(tint: Color(hex: "#8D939B")))
                }
                .padding(.horizontal, contentInset)
                .padding(.top, contentInset)
                .padding(.bottom, 12)

                Divider()
                    .overlay(Color.white.opacity(0.12))

                List(selection: promptSelectionBinding) {
                    DisclosureGroup(isExpanded: $builtInExpanded) {
                        ForEach(store.filteredBuiltInPrompts) { prompt in
                            PromptBrowserListRow(prompt: prompt)
                                .tag(Optional(prompt.promptId))
                        }
                    } label: {
                        PromptDirectoryHeader(title: "Oletuskriteerit", count: store.filteredBuiltInPrompts.count)
                    }

                    DisclosureGroup(isExpanded: $customExpanded) {
                        ForEach(store.filteredCustomPrompts) { prompt in
                            PromptBrowserListRow(prompt: prompt)
                                .tag(Optional(prompt.promptId))
                        }
                    } label: {
                        PromptDirectoryHeader(title: "Mukautetut kriteerit", count: store.filteredCustomPrompts.count)
                    }
                }
                .scrollContentBackground(.hidden)
                .listStyle(.sidebar)
                .searchable(text: $store.promptSearchText, prompt: "Hae kriteeriä")
                .background(
                    LinearGradient(
                        colors: [
                            Color.black.opacity(0.06),
                            Color.white.opacity(0.10),
                        ],
                        startPoint: .top,
                        endPoint: .bottom
                    )
                )
                .clipShape(RoundedRectangle(cornerRadius: 22, style: .continuous))
                .padding(.top, 10)
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
        }
    }

    private var promptSelectionBinding: Binding<String?> {
        Binding(
            get: { store.selectedLibraryPromptId },
            set: { store.selectLibraryPrompt($0) }
        )
    }
}

struct PromptWorkspaceView: View {
    @EnvironmentObject private var store: GuiStore
    @FocusState private var editorFocused: Bool
    let integrated: Bool
    private let contentInset: CGFloat = 4

    private var selectedPrompt: GuiPromptTemplate? {
        store.selectedPromptFromLibrary
    }

    private var hasDraft: Bool {
        selectedPrompt != nil || !store.draftPromptTitle.isEmpty || !store.draftPromptBody.isEmpty
    }

    private var hasUnsavedChanges: Bool {
        guard let selectedPrompt else {
            return !store.draftPromptTitle.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
                || !store.draftPromptBody.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
        }
        return selectedPrompt.title != store.draftPromptTitle || selectedPrompt.body != store.draftPromptBody
    }

    private var promptLineCount: Int {
        let trimmedBody = store.draftPromptBody.trimmingCharacters(in: .newlines)
        guard !trimmedBody.isEmpty else { return 1 }
        return trimmedBody.components(separatedBy: .newlines).count
    }

    private var detectedPlaceholders: [String] {
        [
            "(STUDENT)",
            "(PROGRESSION)",
            "(OBJECTIVE)",
            "(TARGET)",
            "(ANSWER)",
            "(MODELANSWER)",
            "(MAXPOINTS)",
            "(GROUP)",
            "(STUDENTS)",
            "(CATEGORY)",
            "(EXERCISE NUMBER)",
            "(SWE PHRASE)",
            "(FIN ANSWER)",
        ]
        .filter { store.draftPromptBody.localizedCaseInsensitiveContains($0) }
    }

    var body: some View {
        LibraryPanelShell(integrated: integrated) {
            VStack(alignment: .leading, spacing: 16) {
                HStack(alignment: .top, spacing: 16) {
                    VStack(alignment: .leading, spacing: 5) {
                        Text("Työtila")
                            .font(.system(size: 20, weight: .bold, design: .rounded))
                            .foregroundStyle(.white)
                        Text("Muokkaa valittua kriteeriä suoraan tässä ikkunassa.")
                            .font(.system(size: 12, weight: .medium, design: .rounded))
                            .foregroundStyle(.white.opacity(0.72))
                    }

                    Spacer(minLength: 0)

                    HStack(spacing: 8) {
                        PromptTag(title: store.draftPromptBuiltIn ? "Oletuskriteeri" : "Mukautettu")
                        if hasUnsavedChanges {
                            PromptTag(title: "Muokattu")
                        }

                        Button {
                            editorFocused = true
                        } label: {
                            Label("Muokkaa", systemImage: "square.and.pencil")
                        }
                        .buttonStyle(LiquidGlassButtonStyle(tint: Color(hex: "#7E8A93")))

                        Button {
                            Task { await store.saveCurrentPrompt() }
                        } label: {
                            Label(store.isSavingPrompt ? "Tallennetaan..." : "Tallenna", systemImage: "checkmark")
                        }
                        .buttonStyle(LiquidGlassButtonStyle(tint: Color(hex: "#7A8D83")))
                        .disabled(store.isSavingPrompt || !store.canSavePrompt)
                    }
                }

                Divider()
                    .overlay(Color.white.opacity(0.10))

                ViewThatFits(in: .horizontal) {
                    HStack(spacing: 10) {
                        WorkspaceStatCapsule(label: "Tyyppi", value: store.draftPromptBuiltIn ? "Oletus" : "Mukautettu")
                        WorkspaceStatCapsule(label: "Rivejä", value: "\(promptLineCount)")
                        WorkspaceStatCapsule(label: "Merkkejä", value: "\(store.draftPromptBody.count)")
                        WorkspaceStatCapsule(label: "Paikkamerkkejä", value: "\(detectedPlaceholders.count)")
                    }

                    VStack(alignment: .leading, spacing: 8) {
                        WorkspaceStatCapsule(label: "Tyyppi", value: store.draftPromptBuiltIn ? "Oletus" : "Mukautettu")
                        WorkspaceStatCapsule(label: "Rivejä", value: "\(promptLineCount)")
                        WorkspaceStatCapsule(label: "Merkkejä", value: "\(store.draftPromptBody.count)")
                        WorkspaceStatCapsule(label: "Paikkamerkkejä", value: "\(detectedPlaceholders.count)")
                    }
                }

                if hasDraft {
                    VStack(alignment: .leading, spacing: 10) {
                        Text("Nimi")
                            .font(.system(size: 12, weight: .bold, design: .rounded))
                            .foregroundStyle(.white.opacity(0.76))

                        TextField("Anna kriteerille nimi", text: $store.draftPromptTitle)
                            .textFieldStyle(.plain)
                            .font(.system(size: 14, weight: .semibold, design: .rounded))
                            .foregroundStyle(.white)
                            .padding(.horizontal, 14)
                            .padding(.vertical, 12)
                            .background(Color.black.opacity(0.10))
                            .clipShape(RoundedRectangle(cornerRadius: 18, style: .continuous))
                            .overlay(
                                RoundedRectangle(cornerRadius: 18, style: .continuous)
                                    .stroke(Color.white.opacity(0.08), lineWidth: 1)
                            )
                    }

                    promptEditorCanvas
                        .frame(maxWidth: .infinity, minHeight: 620, alignment: .top)

                    VStack(alignment: .leading, spacing: 10) {
                        Text("Tuetut paikkamerkit")
                            .font(.system(size: 11, weight: .bold, design: .rounded))
                            .foregroundStyle(.white.opacity(0.62))

                        ScrollView(.horizontal) {
                            HStack(spacing: 8) {
                                if detectedPlaceholders.isEmpty {
                                    PromptTag(title: "Ei tunnistettuja paikkamerkkejä")
                                } else {
                                    ForEach(detectedPlaceholders, id: \.self) { placeholder in
                                        PromptTag(title: placeholder)
                                    }
                                }
                            }
                        }
                        .scrollIndicators(.hidden)

                        Text(store.promptPlaceholderHelp)
                            .font(.system(size: 11, weight: .medium, design: .rounded))
                            .foregroundStyle(.white.opacity(0.70))
                    }
                } else {
                    EmptyStateView(
                        title: "Valitse kriteeri",
                        message: "Kun napsautat kirjastosta promptia, sen nimi ja sisältö avautuvat tähän työtilaan."
                    )
                    .frame(maxHeight: .infinity)
                }
            }
            .padding(contentInset)
            .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
        }
    }

    private var promptEditorCanvas: some View {
        WorkspaceCanvas(title: "Muokkaus", subtitle: "Kirjoita, tarkista ja viimeistele arviointikriteeri tässä.") {
            TextEditor(text: $store.draftPromptBody)
                .focused($editorFocused)
                .font(.system(size: 13, weight: .medium, design: .monospaced))
                .scrollContentBackground(.hidden)
                .padding(14)
                .frame(maxWidth: .infinity, maxHeight: .infinity)
                .background(Color.black.opacity(0.10))
                .clipShape(RoundedRectangle(cornerRadius: 22, style: .continuous))
                .overlay(
                    RoundedRectangle(cornerRadius: 22, style: .continuous)
                        .stroke(Color.white.opacity(0.08), lineWidth: 1)
                )
                .foregroundStyle(.white.opacity(0.92))
        }
    }
}

struct LibraryPanelShell<Content: View>: View {
    let integrated: Bool
    @ViewBuilder var content: Content

    init(integrated: Bool, @ViewBuilder content: () -> Content) {
        self.integrated = integrated
        self.content = content()
    }

    var body: some View {
        Group {
            if integrated {
                ZStack {
                    RoundedRectangle(cornerRadius: 28, style: .continuous)
                        .fill(Color.white.opacity(0.08))
                    RoundedRectangle(cornerRadius: 28, style: .continuous)
                        .stroke(Color.white.opacity(0.06), lineWidth: 1)
                    content
                        .padding(18)
                }
            } else {
                GlassCard(fillOpacity: 0.16, strokeOpacity: 0.06) {
                    content
                }
            }
        }
    }
}

struct PromptRowView: View {
    let prompt: GuiPromptTemplate
    let selected: Bool

    var body: some View {
        HStack(spacing: 12) {
            VStack(alignment: .leading, spacing: 4) {
                Text(prompt.title)
                    .font(.system(size: 13, weight: .bold, design: .rounded))
                    .foregroundStyle(.white)

                Text(prompt.builtIn ? "Oletuskriteeri" : "Mukautettu kriteeri")
                    .font(.system(size: 11, weight: .medium, design: .rounded))
                    .foregroundStyle(.white.opacity(0.72))
            }
            Spacer(minLength: 0)
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 12)
        .background(
            RoundedRectangle(cornerRadius: 18, style: .continuous)
                .fill(selected ? Color.white.opacity(0.18) : Color.white.opacity(0.07))
        )
        .overlay(
            RoundedRectangle(cornerRadius: 18, style: .continuous)
                .stroke(Color.white.opacity(selected ? 0.24 : 0.1), lineWidth: 1)
        )
    }
}

struct PromptBrowserListRow: View {
    let prompt: GuiPromptTemplate

    var body: some View {
        HStack(spacing: 10) {
            Image(systemName: prompt.builtIn ? "doc.text.image.fill" : "square.and.pencil")
                .foregroundStyle(prompt.builtIn ? .white.opacity(0.74) : .white.opacity(0.84))
            VStack(alignment: .leading, spacing: 3) {
                Text(prompt.title)
                    .font(.system(size: 13, weight: .semibold, design: .rounded))

                Text(prompt.builtIn ? "Oletuskriteeri" : "Mukautettu kriteeri")
                    .font(.system(size: 11, weight: .medium, design: .rounded))
                    .foregroundStyle(.secondary)
            }
        }
        .padding(.vertical, 3)
    }
}

struct PromptDirectoryHeader: View {
    let title: String
    let count: Int

    var body: some View {
        HStack {
            Text(title)
                .font(.system(size: 12, weight: .bold, design: .rounded))
            Spacer(minLength: 0)
            Text("\(count)")
                .font(.system(size: 11, weight: .bold, design: .rounded))
                .foregroundStyle(.secondary)
        }
    }
}

struct PromptTag: View {
    let title: String

    var body: some View {
        Text(title)
            .font(.system(size: 11, weight: .bold, design: .rounded))
            .foregroundStyle(.white.opacity(0.86))
            .padding(.horizontal, 10)
            .padding(.vertical, 7)
            .background(Color.white.opacity(0.10))
            .clipShape(Capsule())
            .overlay(Capsule().stroke(Color.white.opacity(0.14), lineWidth: 1))
    }
}

struct WorkspaceCanvas<Content: View>: View {
    let title: String
    let subtitle: String
    @ViewBuilder var content: Content

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            VStack(alignment: .leading, spacing: 4) {
                Text(title)
                    .font(.system(size: 14, weight: .bold, design: .rounded))
                    .foregroundStyle(.white)
                Text(subtitle)
                    .font(.system(size: 11, weight: .medium, design: .rounded))
                    .foregroundStyle(.white.opacity(0.68))
            }

            content
                .frame(maxWidth: .infinity, maxHeight: .infinity)
        }
        .padding(16)
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
        .background(Color.white.opacity(0.04))
        .clipShape(RoundedRectangle(cornerRadius: 24, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: 24, style: .continuous)
                .stroke(Color.white.opacity(0.05), lineWidth: 1)
        )
    }
}

struct WorkspaceStatCapsule: View {
    let label: String
    let value: String

    var body: some View {
        LabeledContent {
            Text(value)
                .font(.system(size: 12, weight: .bold, design: .rounded))
                .foregroundStyle(.white)
        } label: {
            Text(label.uppercased())
                .font(.system(size: 10, weight: .bold, design: .rounded))
                .foregroundStyle(.white.opacity(0.58))
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 10)
        .background(Color.black.opacity(0.08))
        .clipShape(RoundedRectangle(cornerRadius: 16, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: 16, style: .continuous)
                .stroke(Color.white.opacity(0.07), lineWidth: 1)
        )
    }
}

struct EmptyStateView: View {
    let title: String
    let message: String

    var body: some View {
        ContentUnavailableView {
            Label(title, systemImage: "sparkles.rectangle.stack")
        } description: {
            Text(message)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .foregroundStyle(.white)
    }
}

extension Color {
    init(hex: String) {
        let hexString = hex.trimmingCharacters(in: CharacterSet.alphanumerics.inverted)
        var int: UInt64 = 0
        Scanner(string: hexString).scanHexInt64(&int)
        let red, green, blue: UInt64
        switch hexString.count {
        case 6:
            (red, green, blue) = (int >> 16, int >> 8 & 0xFF, int & 0xFF)
        default:
            (red, green, blue) = (255, 255, 255)
        }
        self.init(
            .sRGB,
            red: Double(red) / 255.0,
            green: Double(green) / 255.0,
            blue: Double(blue) / 255.0,
            opacity: 1
        )
    }
}
