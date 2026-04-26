from manim import *
import random

class PipelineWorkflow(Scene):
    def construct(self):
        # -------------------------------------------------------------------
        # 0. Intro Title
        # -------------------------------------------------------------------
        title = Text("eDNA Pipeline: Deep Learning & Classification", font_size=32, weight=BOLD)
        self.play(Write(title))
        self.wait(1)
        self.play(title.animate.scale(0.7).to_edge(UP))

        # -------------------------------------------------------------------
        # 1. Preprocessing ATGC Sequences (Fast version)
        # -------------------------------------------------------------------
        raw_seq = Text("NNN-ATGCGATACGCGT-ADAPTER", font_size=28, color=LIGHT_GREY).move_to(ORIGIN)
        self.play(FadeIn(raw_seq))
        
        junk_part = raw_seq[:4]
        adapter_part = raw_seq[17:]
        middle_part = raw_seq[4:17]
        
        clean_seq = Text("ATGCGATACGCGT", font_size=28, color=GREEN_C).move_to(ORIGIN)
        
        qc_label = Text("Quality Trim & Dereplication", font_size=22, color=YELLOW).next_to(raw_seq, DOWN)
        self.play(Write(qc_label))
        
        self.play(
            junk_part.animate.set_color(RED),
            adapter_part.animate.set_color(RED)
        )
        self.play(
            FadeOut(junk_part, shift=DOWN), FadeOut(adapter_part, shift=DOWN), FadeOut(qc_label),
            ReplacementTransform(middle_part, clean_seq)
        )
        self.play(clean_seq.animate.to_edge(LEFT).shift(UP*2))

        # -------------------------------------------------------------------
        # 2. Tokenization & Neural Network (DNABERT-2)
        # -------------------------------------------------------------------
        step2_title = Text("Neural Network Processing (DNABERT-2)", font_size=26, color=PURPLE)
        step2_title.next_to(title, DOWN, buff=0.3)
        self.play(FadeIn(step2_title))

        tokens = VGroup(
            Text("ATGCG", font_size=20, color=YELLOW),
            Text("ATACG", font_size=20, color=ORANGE),
            Text("CGT...", font_size=20, color=RED_C)
        ).arrange(DOWN, buff=0.4).next_to(clean_seq, DOWN, buff=0.5, aligned_edge=LEFT)

        self.play(FadeIn(tokens, shift=RIGHT))

        # Build Neural Network
        # Input (3 nodes), Hidden1 (5 nodes), Hidden2 (5 nodes), Output (2 nodes)
        layers = [3, 5, 5, 2]
        nodes = VGroup()
        for i, num_nodes in enumerate(layers):
            layer_nodes = VGroup(*[Circle(radius=0.15, color=PURPLE_A, fill_opacity=0.7) for _ in range(num_nodes)])
            layer_nodes.arrange(DOWN, buff=0.3)
            nodes.add(layer_nodes)
        
        nodes.arrange(RIGHT, buff=1.0)
        nodes.move_to(ORIGIN).shift(RIGHT*1 + UP*0.2)

        edges = VGroup()
        for i in range(len(layers)-1):
            for n1 in nodes[i]:
                for n2 in nodes[i+1]:
                    edges.add(Line(n1.get_center(), n2.get_center(), stroke_width=1, color=LIGHT_GREY, stroke_opacity=0.3))

        network_group = VGroup(edges, nodes)
        
        self.play(Create(edges), FadeIn(nodes))
        
        # Link tokens to input layer
        token_arrows = VGroup()
        for token, node in zip(tokens, nodes[0]):
            token_arrows.add(Arrow(start=token.get_right(), end=node.get_left(), buff=0.1, color=WHITE, stroke_width=2))
        
        self.play(Create(token_arrows))
        
        # Pulse animation across network
        for i in range(len(layers)):
            self.play(nodes[i].animate.set_color(PINK), run_time=0.3)
            self.play(nodes[i].animate.set_color(PURPLE_A), run_time=0.3)

        # -------------------------------------------------------------------
        # 3. Vector Embeddings in a Graph
        # -------------------------------------------------------------------
        self.play(FadeOut(step2_title), FadeOut(tokens), FadeOut(clean_seq), FadeOut(token_arrows))
        step3_title = Text("Dense Embeddings mapped to Vector Space", font_size=26, color=TEAL)
        step3_title.next_to(title, DOWN, buff=0.3)
        self.play(FadeIn(step3_title))

        vector_text = Text("[ 0.82,  0.55 ]", font_size=24, color=TEAL)
        vector_text.move_to(ORIGIN)

        self.play(
            FadeOut(edges),
            FadeOut(nodes[:-1]),
            ReplacementTransform(nodes[-1], vector_text)
        )
        self.wait(1)

        # Create Graph
        axes = Axes(
            x_range=[-1.5, 1.5, 1],
            y_range=[-1.5, 1.5, 1],
            x_length=4,
            y_length=4,
            axis_config={"color": BLUE}
        ).move_to(ORIGIN).shift(DOWN*0.5)

        self.play(
            vector_text.animate.to_edge(LEFT).shift(UP*0.5),
            Create(axes)
        )

        vector_target = axes.coords_to_point(0.82, 0.55)
        vec_arrow = Arrow(start=axes.c2p(0, 0), end=vector_target, buff=0, color=TEAL)
        vec_dot = Dot(vector_target, color=TEAL)
        
        eq_label = Text("x = 0.82, y = 0.55", font_size=16, color=TEAL).next_to(vec_dot, UR, buff=0.1)

        self.play(Create(vec_arrow), FadeIn(vec_dot))
        self.play(Write(eq_label))
        self.wait(1)

        # -------------------------------------------------------------------
        # 4. Neural Classifier Operation Visual
        # -------------------------------------------------------------------
        self.play(FadeOut(step3_title), FadeOut(vector_text))
        step4_title = Text("Classifier maps Vectors to Species Clusters", font_size=26, color=ORANGE)
        step4_title.next_to(title, DOWN, buff=0.3)
        self.play(FadeIn(step4_title))

        # Add clusters of points to the graph to show classification regions
        cluster_a = VGroup(*[Dot(axes.c2p(random.uniform(0.4, 1.2), random.uniform(0.3, 1.0)), color=GREEN_C, radius=0.06) for _ in range(15)])
        cluster_b = VGroup(*[Dot(axes.c2p(random.uniform(-1.2, -0.3), random.uniform(-1.0, 0.2)), color=RED_C, radius=0.06) for _ in range(15)])
        cluster_c = VGroup(*[Dot(axes.c2p(random.uniform(0.2, 1.2), random.uniform(-1.2, -0.5)), color=YELLOW, radius=0.06) for _ in range(15)])

        self.play(FadeIn(cluster_a), FadeIn(cluster_b), FadeIn(cluster_c))

        # Decision boundary drawing
        boundary_1 = Line(axes.c2p(-1.5, 0), axes.c2p(1.5, 0.2), color=LIGHT_GREY, stroke_width=2).set_opacity(0.6)
        boundary_2 = Line(axes.c2p(0, 1.5), axes.c2p(0.2, -1.5), color=LIGHT_GREY, stroke_width=2).set_opacity(0.6)
        
        self.play(Create(boundary_1), Create(boundary_2))
        self.wait(1)

        target_circle = Circle(radius=0.4, color=TEAL).move_to(vector_target)
        self.play(Create(target_circle))
        
        class_res = Text("Classified as: Pelagibacter ubique", font_size=20, color=GREEN_C).next_to(axes, RIGHT, buff=0.5)
        self.play(Write(class_res))
        self.wait(1)

        # -------------------------------------------------------------------
        # 5. Taxonomy Pie Chart
        # -------------------------------------------------------------------
        self.play(
            FadeOut(step4_title), FadeOut(axes), FadeOut(vec_arrow), FadeOut(vec_dot), FadeOut(eq_label),
            FadeOut(cluster_a), FadeOut(cluster_b), FadeOut(cluster_c), FadeOut(boundary_1), FadeOut(boundary_2),
            FadeOut(target_circle), FadeOut(class_res)
        )
        
        step5_title = Text("Final Ecosystem Taxonomy Distribution", font_size=26, color=BLUE_C)
        step5_title.next_to(title, DOWN, buff=0.3)
        self.play(FadeIn(step5_title))

        # Pie chart using Sectors
        # Colors & data
        pie_data = [
            ("Pelagibacter (45%)", 0.45 * 2*PI, GREEN_C),
            ("Vibrio (25%)", 0.25 * 2*PI, ORANGE),
            ("Unknown/Novel (20%)", 0.20 * 2*PI, PURPLE),
            ("Thalassiosira (10%)", 0.10 * 2*PI, BLUE_C)
        ]
        
        start_ang = 0
        pie_chart = VGroup()
        labels = VGroup()
        
        radius = 1.8
        
        for name, angle, color in pie_data:
            sector = Sector(radius=radius, angle=angle, start_angle=start_ang, color=color, stroke_width=2, stroke_color=WHITE)
            pie_chart.add(sector)
            
            # Position label directionally from the edge
            mid_angle = start_ang + angle/2
            dir_vec = np.array([np.cos(mid_angle), np.sin(mid_angle), 0])
            anchor = ORIGIN + dir_vec * radius
            
            label_text = Text(name, font_size=16, color=color)
            label_text.next_to(anchor, dir_vec, buff=0.2)
            labels.add(label_text)
            
            start_ang += angle

        pie_group = VGroup(pie_chart, labels).move_to(ORIGIN).shift(DOWN*0.5)

        # Animate sectors appearing
        for sector, label in zip(pie_chart, labels):
            self.play(Create(sector), run_time=0.5)
            self.play(Write(label), run_time=0.3)
        
        self.wait(2)

        # Final fadeout
        self.play(
            *[FadeOut(m) for m in self.mobjects]
        )
        self.wait(1)
