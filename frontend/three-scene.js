// SALESTORM 3D AWS Cloud Architecture Scene (Three.js WebGL)
// Interactive 3D visualization of the complete AWS infrastructure mapped from aws_services.md

class AwsArchitectureScene {
  constructor(containerId) {
    this.container = document.getElementById(containerId);
    this.nodes = [];
    this.connections = [];
    this.particles = [];
    this.fargatePods = [];
    this.autoRotate = true;
    this.selectedNode = null;
    
    this.init();
    this.buildTopology();
    this.setupInteractivity();
    this.animate();
  }

  init() {
    const width = this.container.clientWidth;
    const height = this.container.clientHeight;

    this.scene = new THREE.Scene();
    this.scene.fog = new THREE.FogExp2(0x070a12, 0.012);

    this.camera = new THREE.PerspectiveCamera(45, width / height, 0.1, 1000);
    this.camera.position.set(0, 42, 68);

    this.renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    this.renderer.setSize(width, height);
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    this.renderer.shadowMap.enabled = true;
    this.container.appendChild(this.renderer.domElement);

    this.controls = new THREE.OrbitControls(this.camera, this.renderer.domElement);
    this.controls.enableDamping = true;
    this.controls.dampingFactor = 0.05;
    this.controls.maxPolarAngle = Math.PI / 2.1;
    this.controls.minDistance = 20;
    this.controls.maxDistance = 120;
    this.controls.target.set(0, 5, 0);

    // Lighting
    const ambientLight = new THREE.AmbientLight(0xffffff, 0.6);
    this.scene.add(ambientLight);

    const dirLight = new THREE.DirectionalLight(0x00f2fe, 1.2);
    dirLight.position.set(30, 50, 40);
    this.scene.add(dirLight);

    const dirLight2 = new THREE.DirectionalLight(0xa855f7, 0.8);
    dirLight2.position.set(-30, 40, -30);
    this.scene.add(dirLight2);

    // Ground Grid
    const grid = new THREE.GridHelper(120, 40, 0x00f2fe, 0x1e293b);
    grid.position.y = -2;
    grid.material.opacity = 0.25;
    grid.material.transparent = true;
    this.scene.add(grid);

    window.addEventListener('resize', () => this.onResize());
  }

  onResize() {
    if (!this.container) return;
    const width = this.container.clientWidth;
    const height = this.container.clientHeight;
    this.camera.aspect = width / height;
    this.camera.updateProjectionMatrix();
    this.renderer.setSize(width, height);
  }

  // Create VPC Planes and Service Nodes
  buildTopology() {
    // 1. VPC Boundary Floor (10.0.0.0/16)
    const vpcGeo = new THREE.PlaneGeometry(85, 48);
    const vpcMat = new THREE.MeshBasicMaterial({
      color: 0x0284c7,
      transparent: true,
      opacity: 0.05,
      side: THREE.DoubleSide
    });
    const vpcMesh = new THREE.Mesh(vpcGeo, vpcMat);
    vpcMesh.rotation.x = -Math.PI / 2;
    vpcMesh.position.set(0, -1.8, 5);
    this.scene.add(vpcMesh);

    // VPC Wireframe Border
    const vpcEdges = new THREE.EdgesGeometry(vpcGeo);
    const vpcLine = new THREE.LineSegments(vpcEdges, new THREE.MeshBasicMaterial({ color: 0x38bdf8, transparent: true, opacity: 0.3 }));
    vpcLine.rotation.x = -Math.PI / 2;
    vpcLine.position.set(0, -1.8, 5);
    this.scene.add(vpcLine);

    // 2. Subnet Planes
    this.createSubnetPlane(-24, 8, 30, 24, 0x00f5a0, "Public Subnet (ALB Ingress)");
    this.createSubnetPlane(0, 8, 36, 24, 0x38bdf8, "Private App Subnet (ECS Fargate)");
    this.createSubnetPlane(26, 8, 30, 24, 0xa855f7, "Private Data Subnet (RDS & Redis)");

    // 3. Service Nodes mapping all 12 services
    // Client & Edge Tier (Outside VPC)
    this.addNode({
      id: "clients",
      title: "10,000 Flash-Sale Clients",
      category: "Ingress",
      pos: [-38, 4, 8],
      color: 0x00f2fe,
      geo: new THREE.SphereGeometry(1.6, 24, 24)
    });

    this.addNode({
      id: "route53",
      title: "Amazon Route 53 (DNS)",
      category: "Edge Routing",
      pos: [-32, 7, 8],
      color: 0x38bdf8,
      geo: new THREE.OctahedronGeometry(1.4)
    });

    this.addNode({
      id: "cloudfront-waf",
      title: "CloudFront CDN + AWS WAF",
      category: "Edge & DDoS Shield",
      pos: [-25, 9, 8],
      color: 0xf43f5e,
      geo: new THREE.BoxGeometry(2.4, 2.4, 2.4)
    });

    // Public Subnet - Application Load Balancer
    this.addNode({
      id: "alb",
      title: "Application Load Balancer (salestorm-alb)",
      category: "Load Balancing",
      pos: [-16, 5, 8],
      color: 0x00f5a0,
      geo: new THREE.DodecahedronGeometry(2.2)
    });

    // Private App Subnet - ECS Fargate Cluster
    this.fargateClusterPos = [-2, 5, 8];
    this.addNode({
      id: "ecs-cluster",
      title: "Amazon ECS Fargate Cluster",
      category: "Serverless Containers",
      pos: this.fargateClusterPos,
      color: 0x00f5a0,
      geo: new THREE.CylinderGeometry(4.5, 4.5, 0.6, 32),
      isBase: true
    });

    // Initial 2 Baseline Fargate Tasks
    this.createFargateTasks(2);

    // Private Data Subnet - Redis 7.x & RDS PostgreSQL 16
    this.addNode({
      id: "elasticache-redis",
      title: "Amazon ElastiCache Redis 7",
      category: "Atomic Lua Scarcity Arbiter",
      pos: [20, 5, 2],
      color: 0xf59e0b,
      geo: new THREE.CylinderGeometry(2, 2, 3.5, 24)
    });

    this.addNode({
      id: "rds-postgres",
      title: "Amazon RDS PostgreSQL 16 (Multi-AZ)",
      category: "ACID Relational Storage",
      pos: [20, 5, 14],
      color: 0xa855f7,
      geo: new THREE.CylinderGeometry(2.2, 2.2, 4.2, 24)
    });

    // Supporting Services Tier (Lower Section)
    this.addNode({
      id: "ecr",
      title: "Amazon ECR (Image Registry)",
      category: "DevOps & Containers",
      pos: [-14, 3, -12],
      color: 0xf97316,
      geo: new THREE.BoxGeometry(2.2, 2.2, 2.2)
    });

    this.addNode({
      id: "secrets-manager",
      title: "AWS Secrets Manager",
      category: "Zero-Trust Security",
      pos: [0, 3, -12],
      color: 0xf43f5e,
      geo: new THREE.OctahedronGeometry(1.6)
    });

    this.addNode({
      id: "cloudwatch",
      title: "Amazon CloudWatch Logs & Metrics",
      category: "Observability",
      pos: [14, 3, -12],
      color: 0xec4899,
      geo: new THREE.IcosahedronGeometry(1.8)
    });

    this.addNode({
      id: "sns",
      title: "Amazon SNS Alerting",
      category: "Notification Bus",
      pos: [24, 3, -12],
      color: 0x8b5cf6,
      geo: new THREE.SphereGeometry(1.4, 20, 20)
    });

    // 4. Construct Connection Pipelines & Data Flow Beams
    this.connectNodes("clients", "route53", 0x00f2fe);
    this.connectNodes("route53", "cloudfront-waf", 0x38bdf8);
    this.connectNodes("cloudfront-waf", "alb", 0x00f5a0);
    this.connectNodes("alb", "ecs-cluster", 0x00f5a0);
    this.connectNodes("ecs-cluster", "elasticache-redis", 0xf59e0b);
    this.connectNodes("ecs-cluster", "rds-postgres", 0xa855f7);
    this.connectNodes("ecs-cluster", "secrets-manager", 0xf43f5e, true);
    this.connectNodes("ecs-cluster", "ecr", 0xf97316, true);
    this.connectNodes("ecs-cluster", "cloudwatch", 0xec4899, true);
    this.connectNodes("cloudwatch", "sns", 0x8b5cf6, true);
  }

  createSubnetPlane(x, z, width, depth, color, name) {
    const geo = new THREE.PlaneGeometry(width, depth);
    const mat = new THREE.MeshBasicMaterial({
      color: color,
      transparent: true,
      opacity: 0.08,
      side: THREE.DoubleSide
    });
    const mesh = new THREE.Mesh(geo, mat);
    mesh.rotation.x = -Math.PI / 2;
    mesh.position.set(x, -1.6, z);
    this.scene.add(mesh);

    const edges = new THREE.EdgesGeometry(geo);
    const wire = new THREE.LineSegments(edges, new THREE.MeshBasicMaterial({ color: color, transparent: true, opacity: 0.35 }));
    wire.rotation.x = -Math.PI / 2;
    wire.position.set(x, -1.6, z);
    this.scene.add(wire);
  }

  addNode(data) {
    const group = new THREE.Group();
    group.position.set(...data.pos);

    // Core mesh
    const mat = new THREE.MeshStandardMaterial({
      color: data.color,
      roughness: 0.2,
      metalness: 0.8,
      emissive: data.color,
      emissiveIntensity: 0.35
    });
    const mesh = new THREE.Mesh(data.geo, mat);
    mesh.castShadow = true;
    group.add(mesh);

    // Glowing Halo Wireframe
    if (!data.isBase) {
      const wireMat = new THREE.MeshBasicMaterial({ color: data.color, wireframe: true, transparent: true, opacity: 0.3 });
      const haloGeo = data.geo.clone();
      haloGeo.scale(1.25, 1.25, 1.25);
      const halo = new THREE.Mesh(haloGeo, wireMat);
      group.add(halo);
      group.halo = halo;
    }

    // Floating Ground Indicator Ring
    const ringGeo = new THREE.RingGeometry(1.6, 2.2, 32);
    const ringMat = new THREE.MeshBasicMaterial({ color: data.color, side: THREE.DoubleSide, transparent: true, opacity: 0.35 });
    const ring = new THREE.Mesh(ringGeo, ringMat);
    ring.rotation.x = -Math.PI / 2;
    ring.position.y = -data.pos[1] - 1.5;
    group.add(ring);

    group.userData = data;
    this.scene.add(group);
    this.nodes.push(group);
    return group;
  }

  createFargateTasks(count) {
    // Remove old tasks
    this.fargatePods.forEach(pod => this.scene.remove(pod));
    this.fargatePods = [];

    const radius = 3.2;
    for (let i = 0; i < count; i++) {
      const angle = (i / count) * Math.PI * 2;
      const x = this.fargateClusterPos[0] + Math.cos(angle) * radius;
      const z = this.fargateClusterPos[2] + Math.sin(angle) * radius;
      const y = this.fargateClusterPos[1] + 1.8;

      const podGroup = new THREE.Group();
      podGroup.position.set(x, y, z);

      const podGeo = new THREE.BoxGeometry(1.2, 1.8, 1.2);
      const podMat = new THREE.MeshStandardMaterial({
        color: 0x00f5a0,
        emissive: 0x00f5a0,
        emissiveIntensity: 0.5,
        roughness: 0.1,
        metalness: 0.9
      });
      const podMesh = new THREE.Mesh(podGeo, podMat);
      podGroup.add(podMesh);

      // Pulse ring
      const ringGeo = new THREE.RingGeometry(0.8, 1.1, 16);
      const ringMat = new THREE.MeshBasicMaterial({ color: 0x00f5a0, side: THREE.DoubleSide, transparent: true, opacity: 0.4 });
      const ring = new THREE.Mesh(ringGeo, ringMat);
      ring.rotation.x = -Math.PI / 2;
      ring.position.y = -1.2;
      podGroup.add(ring);

      podGroup.userData = { id: `fargate-task-${i+1}`, title: `ECS Fargate Task Replica ${i+1}`, category: "Container Instance" };
      this.scene.add(podGroup);
      this.fargatePods.push(podGroup);
    }
  }

  connectNodes(fromId, toId, color, isDashed = false) {
    const from = this.nodes.find(n => n.userData.id === fromId);
    const to = this.nodes.find(n => n.userData.id === toId);
    if (!from || !to) return;

    const p1 = from.position.clone();
    const p2 = to.position.clone();
    const mid = new THREE.Vector3().addVectors(p1, p2).multiplyScalar(0.5);
    mid.y += 2.5;

    const curve = new THREE.QuadraticBezierCurve3(p1, mid, p2);
    const points = curve.getPoints(30);
    const geometry = new THREE.BufferGeometry().setFromPoints(points);

    const material = isDashed ?
      new THREE.LineDashedMaterial({ color: color, dashSize: 0.8, gapSize: 0.4, transparent: true, opacity: 0.6 }) :
      new THREE.LineBasicMaterial({ color: color, transparent: true, opacity: 0.65, linewidth: 2 });

    const line = new THREE.Line(geometry, material);
    if (isDashed) line.computeLineDistances();
    this.scene.add(line);

    this.connections.push({ curve, color });
    this.spawnParticle(curve, color);
  }

  spawnParticle(curve, color) {
    const geo = new THREE.SphereGeometry(0.35, 12, 12);
    const mat = new THREE.MeshBasicMaterial({ color: color });
    const mesh = new THREE.Mesh(geo, mat);
    this.scene.add(mesh);

    this.particles.push({
      mesh,
      curve,
      progress: Math.random(),
      speed: 0.008 + Math.random() * 0.006
    });
  }

  // Trigger high-velocity data packet burst during tests
  triggerPacketBurst() {
    this.connections.forEach(conn => {
      for (let i = 0; i < 3; i++) {
        this.spawnParticle(conn.curve, conn.color);
      }
    });

    // Cleanup extra particles after 4 seconds
    setTimeout(() => {
      while (this.particles.length > this.connections.length * 2) {
        const p = this.particles.pop();
        if (p && p.mesh) this.scene.remove(p.mesh);
      }
    }, 4000);
  }

  setupInteractivity() {
    this.raycaster = new THREE.Raycaster();
    this.mouse = new THREE.Vector2();

    this.renderer.domElement.addEventListener('pointerdown', (e) => {
      const rect = this.renderer.domElement.getBoundingClientRect();
      this.mouse.x = ((e.clientX - rect.left) / rect.width) * 2 - 1;
      this.mouse.y = -((e.clientY - rect.top) / rect.height) * 2 + 1;

      this.raycaster.setFromCamera(this.mouse, this.camera);
      const allObjects = [...this.nodes, ...this.fargatePods];
      const intersects = this.raycaster.intersectObjects(allObjects, true);

      if (intersects.length > 0) {
        let root = intersects[0].object;
        while (root.parent && root.parent !== this.scene) {
          root = root.parent;
        }
        if (root.userData && root.userData.id) {
          this.selectNode(root);
        }
      }
    });
  }

  selectNode(group) {
    if (this.selectedNode && this.selectedNode.halo) {
      this.selectedNode.halo.scale.set(1.25, 1.25, 1.25);
    }
    this.selectedNode = group;
    if (group.halo) {
      group.halo.scale.set(1.6, 1.6, 1.6);
    }

    if (window.showServiceSpecModal) {
      window.showServiceSpecModal(group.userData.id);
    }
  }

  setCameraView(viewName) {
    if (viewName === 'default') {
      this.camera.position.set(0, 42, 68);
      this.controls.target.set(0, 5, 0);
    } else if (viewName === 'topdown') {
      this.camera.position.set(0, 85, 5);
      this.controls.target.set(0, 0, 5);
    } else if (viewName === 'compute') {
      this.camera.position.set(-2, 16, 26);
      this.controls.target.set(-2, 6, 8);
    } else if (viewName === 'data') {
      this.camera.position.set(22, 16, 28);
      this.controls.target.set(20, 5, 8);
    }
  }

  animate() {
    requestAnimationFrame(() => this.animate());

    // Rotate halos and nodes
    this.nodes.forEach(node => {
      if (node.halo) node.halo.rotation.y += 0.01;
      if (node.children[0] && !node.userData.isBase) {
        node.children[0].rotation.y += 0.005;
      }
    });

    // Fargate pods floating bounce
    const time = Date.now() * 0.003;
    this.fargatePods.forEach((pod, idx) => {
      pod.position.y += Math.sin(time + idx) * 0.006;
      pod.rotation.y += 0.012;
    });

    // Animate data packet particles
    this.particles.forEach(p => {
      p.progress += p.speed;
      if (p.progress >= 1) p.progress = 0;
      const pos = p.curve.getPoint(p.progress);
      p.mesh.position.copy(pos);
    });

    this.controls.update();
    this.renderer.render(this.scene, this.camera);
  }
}

window.AwsArchitectureScene = AwsArchitectureScene;
